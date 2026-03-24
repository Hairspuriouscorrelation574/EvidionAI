import json
import logging
import os
import uuid
import shutil
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import docker

from utils.schema import AgentState
from .prompt import CODE_AGENT_PROMPTS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CodeAgent:
    """
    Code generation and execution agent with Docker and iterative self-fixing.
    The agent produces both code and its dependencies (requirements) in a structured format.
    """

    def __init__(self, llm: Any, docker_client=None, max_attempts: int = 3):
        self.llm = llm
        self.docker_client = docker_client or docker.from_env()
        self.max_attempts = max_attempts
        self.code_history = []

        self._docker_login()

    def _docker_login(self):
        username = os.getenv('DOCKER_USERNAME')
        password = os.getenv('DOCKER_PASSWORD')

        if username and password:
            try:
                self.docker_client.login(username=username, password=password)
                logger.info(f"Successfully logged into Docker registry 'Docker Hub'")
            except Exception as e:
                logger.error(f"Docker login failed: {e}")
        else:
            logger.info("No Docker credentials provided, proceeding without login.")

    def analyze_code_requirements(self, query: str, instructions: str, context: List[Dict] = None, code: str = None) -> List[str]:
        """
        Analyze the user query and instructions to produce a requirements summary.
        Returns a string (analysis) that will be passed to code generation.
        """
        context_str = json.dumps(context, ensure_ascii=False) if context else "No context available"
        prompt = CODE_AGENT_PROMPTS["requirements_analysis"].format(
            query=query,
            instructions=instructions,
            code_data=code,
            context=context_str
        )
        analysis = self.llm.invoke(prompt)
        return [analysis, prompt]

    def _parse_code_response(self, response: str) -> Tuple[str, List[str]]:
        """
        Parse the LLM response expecting JSON with 'code' and 'requirements' fields.
        Falls back to treating the whole response as code and empty requirements.
        """
        try:
            if "{" in response and "}" in response:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                
                code = data.get("code", "").strip()
                reqs = data.get("requirements", [])
                if isinstance(reqs, list) and all(isinstance(r, str) for r in reqs):
                    return code, reqs
                else:
                    logger.warning("Requirements field is not a list of strings, using empty list")
                    return code, []
        except:
            logger.info(f"Error in parsing supervisor agent JSON on decision: {response}") 
            return response.strip(), []

    def generate_initial_code(self, requirements: str, query: str,
                              instructions: str, context: List[Dict] = None, code: str = None) -> Tuple[Tuple[str, List[str]], str]:
        """
        Generate the first version of the code and its dependencies.
        Returns (code, list_of_requirements).
        """
        context_str = json.dumps(context, ensure_ascii=False) if context else "No context available"
        prompt = CODE_AGENT_PROMPTS["code_generation"].format(
            requirements=requirements,
            query=query,
            instructions=instructions,
            code_data=code,
            context=context_str
        )
        response = self.llm.invoke(prompt)
        return [self._parse_code_response(response), prompt, response]

    def _fix_code_with_history(self,
                               previous_code: str,
                               previous_reqs: List[str],
                               execution_result: Dict,
                               history: List[Dict],
                               requirements: str,
                               query: str,
                               instructions: str,
                               context: List[Dict] = None) -> Tuple[Tuple[str, List[str]], str]:
        """
        Generate a fixed version of the code using the error and the full history of previous attempts.
        Returns (new_code, new_requirements).
        """
        context_str = json.dumps(context, ensure_ascii=False) if context else "No context available"
        history_str = "\n\n".join(
            f"Attempt {i+1}:\n"
            f"Code:\n```\n{attempt['code']}\n```\n"
            f"Requirements: {attempt.get('requirements', [])}\n"
            f"Result: {'Success' if attempt['success'] else 'Error'}\n"
            f"Error output: {attempt.get('error', 'None')}\n"
            f"Standard output: {attempt.get('stdout', '')}"
            for i, attempt in enumerate(history)
        )

        prompt = CODE_AGENT_PROMPTS.get("code_fix", CODE_AGENT_PROMPTS["code_generation"]).format(
            previous_code=previous_code,
            previous_requirements=previous_reqs,
            error=execution_result['error'],
            history=history_str,
            requirements=requirements,
            query=query,
            instructions=instructions,
            context=context_str
        )
        response = self.llm.invoke(prompt)
        return [self._parse_code_response(response), prompt, response]

    def _cleanup_own_resources(self, container=None, container_run_dir: str = None,
                                run_id: str = None):
        """
        Clean up everything this execution created:
        - Stop + remove the container (force)
        - Remove the temp directory on the host volume
        - Remove any dangling containers with our label that are already stopped
        Does NOT touch system images, volumes, or containers we didn't create.
        """
        if container:
            try:
                container.stop(timeout=1)
            except Exception:
                pass
            try:
                container.remove(force=True)
            except Exception:
                pass

        if container_run_dir:
            try:
                shutil.rmtree(container_run_dir, ignore_errors=True)
            except Exception:
                pass

        try:
            stale = self.docker_client.containers.list(
                all=True,
                filters={"label": "evidion.managed=true", "status": "exited"}
            )
            for c in stale:
                try:
                    c.remove(force=True)
                    logger.info(f"Cleaned up stale container: {c.short_id}")
                except Exception:
                    pass
        except Exception:
            pass

    def _execute_code_in_docker(self, code: str, requirements: List[str]) -> Dict:
        """
        Execute the given code inside a Docker container.
        Returns a dict with stdout, stderr, exit_code, success, error, urls_used.
        Cleans up all own resources (container, temp files) in finally block.
        """
        run_id = str(uuid.uuid4())[:8]
        base_dir = "/ai_agents_service_data"
        container_run_dir = os.path.join(base_dir, run_id)
        
        os.makedirs(container_run_dir, exist_ok=True)

        with open(os.path.join(container_run_dir, "script.py"), "w", encoding="utf-8") as f:
            f.write(code)

        with open(os.path.join(container_run_dir, "requirements.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(requirements) if requirements else "")

        volumes = {'ai_agents_service': {'bind': '/app', 'mode': 'rw'}}
        work_dir = f"/app/{run_id}"
        install_cmd = f"pip install -q -r {work_dir}/requirements.txt" if requirements else "echo 'No requirements'"
        full_command = f"sh -c '{install_cmd} && python -u {work_dir}/script.py'"

        container = None
        try:
            container = self.docker_client.containers.run(
                image='pytorch/pytorch:latest',
                command=full_command,
                environment={"PYTHONUNBUFFERED": "1"},
                volumes=volumes,
                working_dir='/app',
                detach=True,
                stdout=True,
                stderr=True,
                remove=False,
                mem_limit='8g',
                nano_cpus=4_000_000_000,
                network_disabled=False,
                labels={"evidion.managed": "true", "evidion.run_id": run_id}
            )

            try:
                result = container.wait()
                exit_code = result["StatusCode"]
            except Exception:
                exit_code = -1

            stdout = container.logs(stdout=True,  stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "success": exit_code == 0,
                "error": stderr if exit_code != 0 else "None",
            }

        except Exception as e:
            logger.error("Docker execution error: %r", e)
            return {"stdout": "", 
                    "stderr": str(e), 
                    "exit_code": -1,
                    "success": False, 
                    "error": str(e)}

        finally:
            self._cleanup_own_resources(container, container_run_dir, run_id)

    def analyze_final_code(self,
                           code: str,
                           requirements: List[str],
                           requirements_analysis: str,
                           execution_result: Optional[Dict],
                           history: List[Dict]) -> List[str]:
        """
        Perform a detailed analysis of the final code, including execution results and attempt history.
        """
        history_str = "\n".join(
            f"Attempt {i+1}: {'success' if a['success'] else 'failure'} – {a.get('error', '')[:100]}"
            for i, a in enumerate(history)
        )
        prompt = CODE_AGENT_PROMPTS["code_analysis"].format(
            code=code,
            requirements=requirements_analysis,
            execution_stdout=(execution_result or {}).get('stdout', ''),
            execution_stderr=(execution_result or {}).get('stderr', ''),
            execution_success=(execution_result or {}).get('success', False),
            history=history_str
        )
        return [self.llm.invoke(prompt), prompt]

    def run(self, state: AgentState) -> Dict[str, Any]:
        """
        Main entry point: generate code, execute it iteratively with fixes, and return final solution.
        """
        logger.info("💻 Code Agent activated...")

        query = state["user_input"]
        instructions = state["supervisor_instructions"][-1]
        try:
            code = state["code_solutions"][-1]["final_code"]
        except:
            code = None
        context = state.get("search_results", [])

        logger.info("📋 Analyzing requirements...")
        requirements_analysis, prompt_analyze = self.analyze_code_requirements(query, instructions, context, code)

        logger.info("⚙️ Generating initial code...")
        data, prompt_code, response_code = self.generate_initial_code(requirements_analysis, query, instructions, context, code)
        code, requirements_list = data

        attempts_history = []
        execution_result = None
        final_code = code
        final_requirements = requirements_list
        fix_code_history = []

        for attempt_num in range(1, self.max_attempts + 1):
            logger.info(f"🚀 Attempt {attempt_num}: executing code in Docker...")
            execution_result = self._execute_code_in_docker(final_code, final_requirements)

            attempt_record = {
                "code": final_code,
                "requirements": final_requirements,
                "success": execution_result['success'],
                "stdout": execution_result['stdout'],
                "stderr": execution_result['stderr'],
                "error": execution_result['error'],
                "exit_code": execution_result['exit_code']
            }
            attempts_history.append(attempt_record)

            if execution_result['success']:
                logger.info(f"✅ Code executed successfully on attempt {attempt_num}.")
                break
            else:
                logger.warning(f"❌ Execution failed: {execution_result['error'][:200]}")
                if attempt_num < self.max_attempts:
                    logger.info("🛠️  Fixing code with history context...")
                    data, prompt_fix, response_fix = self._fix_code_with_history(
                        previous_code=final_code,
                        previous_reqs=final_requirements,
                        execution_result=execution_result,
                        history=attempts_history,
                        requirements=requirements_analysis,
                        query=query,
                        instructions=instructions,
                        context=context
                    )

                    final_code, final_requirements = data

                    fix_code_history.append([
                        {"role": "Code Agent to Code Agent", "content": prompt_fix},
                        {"role": "Code Agent", "content": response_fix}
                    ])
                else:
                    logger.error("🔴 Max attempts reached. Proceeding with the last version.")

        logger.info("🔍 Analyzing final code and execution results...")
        code_analysis, prompt_final = self.analyze_final_code(
            final_code, final_requirements, requirements_analysis, execution_result, attempts_history
        )

        solution = {
            "requirements_analysis": requirements_analysis,
            "code": final_code,
            "requirements_list": final_requirements,
            "execution_result": execution_result,
            "analysis": code_analysis,
            "attempts_history": attempts_history,
            "attempts_made": len(attempts_history)
        }
        self.code_history.append(solution)

        history = [{"role": "Supervisor to Code Agent", "content": prompt_analyze},
                   {"role": "Code Agent", "content": requirements_analysis},
                   {"role": "Code Agent to Code Agent", "content": prompt_code},
                   {"role": "Code Agent", "content": response_code}
                   ] + fix_code_history + [
                       {"role": "Code Agent to Code Agent", "content": prompt_final},
                       {"role": "Code Agent", "content": code_analysis}
                       ]

        return {
            "code_solutions": state.get("code_solutions", []) + [solution],
            "current_agent": "supervisor",
            "messages": state["messages"] + [
                {"role": "assistant (code agent)",
                 "content": f"Code Agent finished: attempts={len(attempts_history)}, success={execution_result['success']}. Code analysis is available at 'Code Solutions'."}
            ],
            "history": state["history"] + history,
            "last_update": datetime.now().isoformat()
        }
    