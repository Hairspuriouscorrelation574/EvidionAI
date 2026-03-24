# Contributing to EvidionAI

Thank you for your interest in contributing! Whether you're fixing a bug, adding a new agent, or improving the docs — all contributions are welcome.

## Getting started

1. Fork the repository on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/Evidion-AI/EvidionAI.git
   cd EvidionAI
   ```
3. Set up your environment:
   ```bash
   bash install.sh
   ```
4. Create a feature branch:
   ```bash
   git checkout -b feature/my-feature
   ```

## Code style

- **Python** — PEP 8, 4-space indentation, 88-character line limit
- **JavaScript** — single quotes, 2-space indentation
- All code and comments must be in **English**
- Use `%s`-style formatting in `logging` calls (not f-strings)
- Each function should do one thing and have a docstring

## Adding a new agent

The agent module is the core of EvidionAI. To add a new agent:

1. Create `ai_agents_service/agents/<name>/agent.py` and `prompt.py`
2. Implement the `run(state: AgentState) -> dict` interface — return only the keys you want to update in the state
3. Register the node in `ai_agents_service/workflow/workflow.py`
4. Add the agent to the routing table in `ai_agents_service/agents/supervisor/prompt.py`

The `AgentState` TypedDict is defined in `ai_agents_service/utils/schema.py` — all agents share it.

## Pull requests

- One feature or fix per PR — keep diffs small and reviewable
- Describe what changed and why in the PR description
- Reference any related issues: `Closes #42`
- Make sure the project still builds: `docker compose up --build`
- If you changed agent prompts, include a sample output showing the effect

## Reporting bugs

Open a [GitHub Issue](https://github.com/Evidion-AI/EvidionAI/issues) and include:

- OS and hardware (CPU/GPU/RAM)
- LLM provider and model name
- The query that caused the issue
- Relevant log output:
  ```bash
  docker compose logs ai_agents_service
  docker compose logs api_gateway
  ```

## Feature requests

Open an issue with the `enhancement` label. Describe the use case, not just the feature — it helps understand the priority and the right way to implement it.

## Areas looking for contributors

- **New agents** — dataset retrieval, citation formatting, web scraping, fact-checking
- **LLM providers** — Gemini, Cohere, Mistral API
- **Evaluation** — benchmark harness for research quality assessment
- **Tests** — unit tests for agents and API routes
- **Docs** — tutorials, worked examples, use-case guides

## Questions

For questions that don't fit an issue, use [GitHub Discussions](https://github.com/Evidion-AI/EvidionAI/discussions).
