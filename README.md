<div align="center">

<img src="frontend/src/favicon.svg" alt="EvidionAI Logo" width="64" height="64"/>

# EvidionAI

**Autonomous Multi-Agent AI Research System**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-orange)](https://langchain-ai.github.io/langgraph/)
[![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![Ollama](https://img.shields.io/badge/Ollama-local%20%26%20cloud-black)](https://ollama.com)
[![OpenAI](https://img.shields.io/badge/OpenAI-compatible-412991?logo=openai&logoColor=white)](https://openai.com)

*Submit a research question. EvidionAI searches literature, writes and runs code, analyzes results, stress-tests its own conclusions, and delivers a structured report — all autonomously.*

[**Quick Start**](#-quick-start) · [**Architecture**](#️-architecture) · [**Agents**](#-agent-system) · [**API**](#-api-reference) · [**Configuration**](#-configuration)

</div>

---

## ✨ What is EvidionAI?

EvidionAI is an open-source **autonomous research assistant** built on a multi-agent LangGraph workflow. It compresses what would take a researcher hours or days — literature search, hypothesis testing, code experimentation, critical review — into a single automated pipeline.

```
User query
    │
    ▼
┌───────────────────────────────────────────────────────────────┐
│                         Supervisor                            │
│  Orchestrates the workflow, routes tasks, assembles report    │
└───┬──────────┬──────────┬──────────┬──────────────────────────┘
    │          │          │          │
    ▼          ▼          ▼          ▼
 Search      Code      Analyze    Skeptic
 Agent       Agent      Agent      Agent
    │          │          │          │
 Literature  Run       Interpret  Challenge
 + Web       experiments results  conclusions
 search
```

The system loops through agents as needed — a typical research query goes through **5–15 agent iterations** before producing a final report.

---

## 🚀 Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose
- One of: **Ollama** (local/cloud), **OpenAI API**, or any OpenAI-compatible endpoint

### Option A — Interactive installer (recommended)

```bash
git clone https://github.com/Evidion-AI/EvidionAI.git
cd EvidionAI
bash install.sh
```

The script asks which LLM provider to use, pulls the right model, writes `.env`, and launches everything.

### Option B — Manual setup

```bash
git clone https://github.com/Evidion-AI/EvidionAI.git
cd EvidionAI
cp env.example .env
# Edit .env with your LLM settings (see Configuration section)
docker compose up --build
```

Open **http://localhost:3000** in your browser.

### Option C — Ollama local in 3 commands

```bash
# 1. Install Ollama: https://ollama.com
ollama pull deepseek-r1:14b

# 2. Clone and configure
git clone https://github.com/Evidion-AI/EvidionAI.git && cd EvidionAI
printf "LLM_PROVIDER=ollama_local\nLLM_MODEL=deepseek-r1:14b\nOLLAMA_HOST=http://host.docker.internal:11434" > .env

# 3. Start
docker compose up --build
```

---

## 🏗️ Architecture

EvidionAI is composed of three Docker services:

```
                    Browser
                       │
                  port 3000
                       │
          ┌────────────▼────────────┐
          │       Frontend          │
          │   nginx + static HTML   │
          └────────────┬────────────┘
                       │ /api/*  (reverse proxy)
          ┌────────────▼────────────┐
          │       API Gateway       │
          │   FastAPI  port 8001    │
          │   REST + SSE endpoints  │
          │   SQLite persistence    │
          └────────────┬────────────┘
                       │ internal
          ┌────────────▼────────────┐
          │   AI Agents Service     │
          │   FastAPI  port 8000    │
          │   LangGraph workflow    │
          │   ChromaDB memory       │
          └─────────────────────────┘
```

Chat and project history is persisted in **SQLite** (mounted as a Docker volume). Long-term semantic memory uses an embedded **ChromaDB** vector store.

### Directory layout

```
EvidionAI/
├── ai_agents_service/          # Multi-agent research engine
│   ├── agents/
│   │   ├── supervisor/         # Orchestrator — routes tasks, assembles report
│   │   ├── search_agent/       # Web + arXiv + Wikipedia search
│   │   ├── code_agent/         # Python code generation + sandboxed execution
│   │   ├── analysis_agent/     # Data analysis and interpretation
│   │   └── skeptic_agent/      # Critical review of conclusions
│   ├── memory/                 # ChromaDB vector memory manager
│   ├── utils/
│   │   ├── llm.py              # Unified LLM provider factory
│   │   ├── llm_utils.py        # Search tools (DDG, arXiv, Wikipedia)
│   │   ├── cancellable_llm.py  # Cancellation-aware LLM wrapper
│   │   └── context_manager.py  # Context compression for long sessions
│   ├── workflow/workflow.py    # LangGraph state machine definition
│   ├── pipeline.py             # MultiAgentChat entry point
│   └── main.py                 # FastAPI service (SSE streaming)
├── backend/
│   └── api/                    # API Gateway
│       ├── db/database.py      # SQLite schema and helpers
│       ├── main.py             # FastAPI app — CORS, Swagger, startup
│       └── routes/
│           ├── ai_agents_api/  # /api/ai/*      — proxy to agents service
│           ├── chats/          # /api/chats/*   — chat + message CRUD
│           ├── projects/       # /api/projects/* — project CRUD
│           └── utils/          # /api/utils/*   — health check
├── frontend/src/               # Static web app (no build step needed)
│   ├── index.html              # Main app shell
│   ├── app.js                  # All frontend logic
│   ├── style.css               # Dark theme styles
│   ├── landing.html            # Landing page
│   └── about.html              # About page
├── docker/                     # Dockerfiles + nginx config
├── docker-compose.yml
├── env.example                 # Annotated configuration reference
├── install.sh                  # Interactive installer
└── README.md
```

---

## 🤖 Agent System

The research workflow is a **LangGraph state machine** where a Supervisor coordinates specialized agents in a loop.

### Supervisor

The central orchestrator. Reads the current state and decides which agent runs next (or stops and writes the final report). It tracks what has been searched, what code has been executed, what the skeptic has challenged, and whether enough evidence has been gathered.

**Routing logic:** `supervisor → {search | code | analyze | skeptic | done}`

### Search Agent

Runs searches across three sources in parallel:
- **DuckDuckGo** — current web results
- **arXiv** — scientific preprints and papers
- **Wikipedia** — background knowledge and definitions

It also fetches and extracts text from relevant URLs. Results are deduplicated and ranked before being passed back to the Supervisor.

### Code Agent

Generates Python code to test hypotheses numerically, run statistical analyses, or build proof-of-concept implementations. Code is executed inside a **sandboxed Docker container** (Docker-in-Docker) — the host system is never touched by agent-generated code.

### Analysis Agent

Interprets results from Search and Code agents. Synthesizes findings into structured insights, identifies patterns, draws conclusions, and flags uncertainties. Runs at a higher temperature (`0.55`) for more creative analytical interpretation.

### Skeptic Agent

Plays devil's advocate. Given the current draft conclusions, it actively looks for:
- Methodological flaws
- Alternative explanations
- Missing evidence
- Overclaims

If the Skeptic raises significant concerns, the Supervisor routes back to Search or Code for another round. This loop continues until the Skeptic is satisfied or the iteration limit is reached.

### Memory System

Each research session is associated with a **memory namespace** (project slug or session id). Previous research results are stored in **ChromaDB** with semantic embeddings (`all-MiniLM-L6-v2`). On future queries in the same namespace, relevant past findings are injected into the agent context — so EvidionAI learns from your previous research within a project.

---

## 🔌 LLM Providers

EvidionAI uses a unified provider factory. Set `LLM_PROVIDER` in `.env` to choose:

| Provider | `LLM_PROVIDER` | Notes |
|---|---|---|
| Ollama local | `ollama_local` | Runs on your machine. Free, private, no rate limits. |
| Ollama Cloud | `ollama_cloud` | Managed API at api.ollama.com. Requires account. |
| OpenAI / compatible | `openai` | OpenAI, Groq, Together, Anthropic proxy, etc. |

### Recommended models

**Ollama Cloud** (`ollama_cloud`):

| Model | Notes |
|---|---|
| `glm-5:cloud` | Best quality — GLM-5 series, strong reasoning |
| `gpt-oss:120b` | Fast, strong reasoning, good for research tasks |
| `gpt-oss:20b` | Lightweight cloud option, lower latency |

**Ollama local** (`ollama_local`):

| Model | RAM required | Notes |
|---|---|---|
| `gpt-oss:20b` | ~14 GB | Best local option if you have the VRAM |
| `deepseek-r1:14b` | ~10 GB | Excellent reasoning, great for research |
| `deepseek-r1:8b` | ~6 GB | Lighter version, good balance |

**OpenAI / compatible** (`openai`):

| Model | Service | Notes |
|---|---|---|
| `gpt-4o` | OpenAI | Top quality |
| `gpt-4o-mini` | OpenAI | Fast and cheap, solid for most queries |
| `o3-mini` | OpenAI | Strong reasoning |
| `claude-3-5-sonnet-20241022` | Anthropic (via proxy) | Excellent analysis quality |
| `llama-3.3-70b-versatile` | Groq | Very fast inference |

---

## 📡 API Reference

All endpoints are under `/api/`. Interactive Swagger docs at **http://localhost:3000/api/docs**.

### Run a research workflow

```http
POST /api/ai/process
Content-Type: application/json

{
  "query": "What are the performance trade-offs between transformers and SSMs for long sequences?",
  "chat_context": [],
  "request_id": "optional-uuid",
  "memory_id": "my-project"
}
```

**Response:** Server-Sent Events stream.

| Event | Payload | Description |
|---|---|---|
| `ping` | `{}` | Keepalive heartbeat every ~15 s |
| `result` | `{ final_answer, full_history }` | Completed research report |
| `error` | `{ final_answer, full_history }` | Fatal error |

#### curl example

```bash
curl -N -X POST http://localhost:3000/api/ai/process \
  -H 'Content-Type: application/json' \
  -d '{"query": "Explain the difference between RLHF and DPO in LLM alignment"}' \
  --no-buffer
```

#### Python example

```python
import httpx
import json

with httpx.Client(timeout=None) as client:
    with client.stream(
        "POST",
        "http://localhost:3000/api/ai/process",
        json={"query": "What is chain-of-thought prompting?"},
    ) as r:
        for line in r.iter_lines():
            if line.startswith("data:") and line != "data: {}":
                data = json.loads(line[5:])
                print(data["final_answer"])
```

### Cancel a running workflow

```http
POST /api/ai/cancel
Content-Type: application/json

{ "request_id": "uuid-from-process-call" }
```

### Chats and projects

```http
GET    /api/projects                    # list projects
POST   /api/projects                    # create project
PUT    /api/projects/{id}               # rename
DELETE /api/projects/{id}               # delete (cascades to chats)

GET    /api/chats                       # list chats (root or ?project_id=)
POST   /api/chats                       # create chat
GET    /api/chats/search?q=...          # full-text search
GET    /api/chats/{id}/messages         # list messages
POST   /api/chats/{id}/messages         # append message
PATCH  /api/chats/{id}/messages/{mid}   # update message
```

### Memory

```http
GET /api/ai/memory/stats?memory_id=my-project
GET /api/ai/memory/recall?memory_id=my-project&q=transformers&k=5
```

### Health

```http
GET /api/health   →   { "status": "ok" }
```

---

## ⚙️ Configuration

All configuration is via environment variables in `.env`. See [`env.example`](env.example) for the full annotated reference.

```env
# LLM provider: ollama_local | ollama_cloud | openai
LLM_PROVIDER=ollama_cloud
LLM_MODEL=glm-5:cloud
LLM_CTX=32768

# Ollama local
OLLAMA_HOST=http://localhost:11434

# Ollama Cloud
OLLAMA_API_KEY=your-key
OLLAMA_BASE_URL=https://api.ollama.com

# OpenAI / compatible
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.groq.com/openai/v1   # optional

# Research
AI_QUERY_MAX_LENGTH=5000
AI_REQUEST_TIMEOUT=14400    # 4 hours
WORKER_THREADS=4

# Frontend
FRONTEND_PORT=3000
ALLOWED_ORIGINS=*           # restrict in production
```

---

## 🛠️ Development

### Run without Docker

```bash
# Terminal 1 — agents service
cd ai_agents_service
pip install -r requirements.txt
cp ../env.example ../.env
uvicorn main:app --port 8000 --reload

# Terminal 2 — API gateway
cd backend/api
pip install -r requirements.txt
uvicorn main:app --port 8001 --reload

# Terminal 3 — frontend (for quick preview only, /api/* won't proxy)
cd frontend/src
python -m http.server 3000
```

For full local dev with proxying, either run nginx with `docker/nginx/nginx.conf` or temporarily point `API_BASE` in `frontend/src/app.js` to `http://localhost:8001`.

### Adding a new agent

1. Create `ai_agents_service/agents/<name>/agent.py` and `prompt.py`
2. Implement the `run(state: AgentState) -> dict` interface
3. Register it in `workflow/workflow.py`
4. Add it to the routing map in `agents/supervisor/prompt.py`

### Ollama on Docker (host networking)

When Ollama runs on your host machine and EvidionAI runs in Docker:

```env
OLLAMA_HOST=http://host.docker.internal:11434
```

This is already the default in `docker-compose.yml` for `ollama_local`.

---

## 🧪 Tested configurations

| Model | Provider | Hardware | Avg. research time |
|---|---|---|---|
| `deepseek-r1:8b` | ollama_local | 16 GB RAM | ~10–20 min |
| `deepseek-r1:14b` | ollama_local | 24 GB RAM | ~15–30 min |
| `gpt-oss:20b` | ollama_local | 32 GB RAM | ~12–25 min |
| `gpt-oss:120b` | ollama_cloud | cloud | ~5–12 min |
| `glm-5:cloud` | ollama_cloud | cloud | ~4–10 min |
| `gpt-4o-mini` | openai | cloud | ~4–10 min |
| `gpt-4o` | openai | cloud | ~5–12 min |

---

## 🤝 Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

Areas where help is especially appreciated:

- **New agents** — dataset retrieval, citation formatting, fact-checking
- **LLM providers** — Gemini, Cohere, Mistral API
- **Evaluation** — benchmark harness for research quality
- **Docs** — tutorials, worked examples, use-case guides

---

## 📄 License

MIT License — see [LICENSE](LICENSE).

---

<div align="center">

Built with ❤️ using [LangGraph](https://langchain-ai.github.io/langgraph/), [FastAPI](https://fastapi.tiangolo.com/), and [Ollama](https://ollama.com/).

**[⭐ Star this repo](https://github.com/Evidion-AI/EvidionAI)** if EvidionAI is useful to you!

Research Paper: https://doi.org/10.13140/RG.2.2.23054.93767

---

*Created by [Nikita Sakovich](https://github.com/NekkittAY) — Research Engineer*

</div>
