#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  EvidionAI — Interactive Installer
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

BOLD='\033[1m'; CYAN='\033[0;36m'; GREEN='\033[0;32m'
YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'

header() { echo -e "\n${CYAN}${BOLD}══ $* ══${RESET}\n"; }
info()   { echo -e "  ${GREEN}✓${RESET} $*"; }
warn()   { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
err()    { echo -e "  ${RED}✗${RESET} $*"; }

clear
echo -e "${CYAN}${BOLD}"
cat << 'BANNER'
  ███████╗██╗   ██╗██╗██████╗ ██╗ ██████╗ ███╗   ██╗ █████╗ ██╗
  ██╔════╝██║   ██║██║██╔══██╗██║██╔═══██╗████╗  ██║██╔══██╗██║
  █████╗  ██║   ██║██║██║  ██║██║██║   ██║██╔██╗ ██║███████║██║
  ██╔══╝  ╚██╗ ██╔╝██║██║  ██║██║██║   ██║██║╚██╗██║██╔══██║██║
  ███████╗ ╚████╔╝ ██║██████╔╝██║╚██████╔╝██║ ╚████║██║  ██║██║
  ╚══════╝  ╚═══╝  ╚═╝╚═════╝ ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝
BANNER
echo -e "${RESET}"
echo -e "  ${BOLD}Autonomous Multi-Agent AI Research System${RESET}"
echo -e "  Open Source · MIT License\n"

# ── Check Docker ──────────────────────────────────────────────────────────────
header "Checking requirements"
if ! command -v docker &>/dev/null; then
  err "Docker not found. Install from: https://docs.docker.com/get-docker/"; exit 1
fi
info "Docker $(docker --version | grep -oP '\d+\.\d+\.\d+' | head -1)"
COMPOSE_CMD="docker compose"
if ! docker compose version &>/dev/null; then
  docker-compose version &>/dev/null && COMPOSE_CMD="docker-compose" || { err "Docker Compose not found."; exit 1; }
fi
info "Docker Compose available"

# ── LLM Provider ──────────────────────────────────────────────────────────────
header "LLM Provider"
echo "  [1] Ollama Cloud   — hosted models via api.ollama.com (recommended)"
echo "  [2] Ollama local   — run models on your own machine   (free, private)"
echo "  [3] OpenAI / compatible API                           (GPT, Claude...)"
echo ""
read -rp "  Choose [1/2/3] (default: 1): " provider_choice
provider_choice="${provider_choice:-1}"

LLM_PROVIDER="" LLM_MODEL="" LLM_CTX=""
OLLAMA_HOST="" OLLAMA_BASE_URL="" OLLAMA_API_KEY=""
OPENAI_API_KEY="" OPENAI_BASE_URL=""

case "$provider_choice" in
  1)
    LLM_PROVIDER="ollama_cloud"
    OLLAMA_BASE_URL="https://api.ollama.com"
    echo ""
    info "Ollama Cloud selected"
    echo ""
    echo "  Recommended models (tested):"
    echo "    glm-5:cloud   — best quality  (GLM-5 series)"
    echo "    gpt-oss:120b  — fast, strong reasoning"
    echo "    gpt-oss:20b   — lightweight option"
    echo ""
    read -rp "  Model (default: glm-5:cloud): " LLM_MODEL
    LLM_MODEL="${LLM_MODEL:-glm-5:cloud}"
    read -rp "  Ollama API key (from ollama.com): " OLLAMA_API_KEY
    [[ -z "$OLLAMA_API_KEY" ]] && { err "API key is required."; exit 1; }
    read -rp "  Context window tokens (default: 32768): " LLM_CTX
    LLM_CTX="${LLM_CTX:-32768}"
    ;;
  2)
    LLM_PROVIDER="ollama_local"
    echo ""
    info "Ollama local selected"
    echo ""
    echo "  Recommended models:"
    echo "    gpt-oss:20b       — if you have enough VRAM"
    echo "    deepseek-r1:14b   — strong reasoning (8 GB RAM)"
    echo "    deepseek-r1:8b    — lighter option   (5 GB RAM)"
    echo "    llama3.1:8b       — good general model (4.7 GB)"
    echo ""
    read -rp "  Model (default: deepseek-r1:14b): " LLM_MODEL
    LLM_MODEL="${LLM_MODEL:-deepseek-r1:14b}"
    read -rp "  Ollama host (default: http://localhost:11434): " OLLAMA_HOST
    OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
    read -rp "  Context window tokens (default: 16384): " LLM_CTX
    LLM_CTX="${LLM_CTX:-16384}"
    echo ""
    if curl -sf "${OLLAMA_HOST}/api/tags" &>/dev/null; then
      info "Ollama is running at ${OLLAMA_HOST}"
      if curl -sf "${OLLAMA_HOST}/api/tags" | grep -q "\"${LLM_MODEL}\""; then
        info "Model '${LLM_MODEL}' is already available"
      else
        warn "Model '${LLM_MODEL}' not found locally."
        read -rp "  Pull it now? [Y/n]: " pull_choice
        if [[ "${pull_choice:-Y}" =~ ^[Yy]$ ]]; then
          echo "  Pulling ${LLM_MODEL}…"
          ollama pull "${LLM_MODEL}" || warn "Pull failed — run 'ollama pull ${LLM_MODEL}' manually."
        fi
      fi
    else
      warn "Cannot reach Ollama at ${OLLAMA_HOST}"
      warn "Make sure Ollama is running: ollama serve"
    fi
    ;;
  3)
    LLM_PROVIDER="openai"
    echo ""
    echo "  [a] OpenAI          (api.openai.com)"
    echo "  [b] Groq            (api.groq.com)"
    echo "  [c] Anthropic proxy or other compatible endpoint"
    echo ""
    read -rp "  Service [a/b/c] (default: a): " svc_choice
    case "${svc_choice:-a}" in
      b) OPENAI_BASE_URL="https://api.groq.com/openai/v1" ;;
      c) read -rp "  Base URL: " OPENAI_BASE_URL ;;
      *) OPENAI_BASE_URL="" ;;
    esac
    echo ""
    echo "  Examples: gpt-4o, gpt-4o-mini, o3-mini, claude-3-5-sonnet-20241022"
    read -rp "  Model (default: gpt-4o-mini): " LLM_MODEL
    LLM_MODEL="${LLM_MODEL:-gpt-4o-mini}"
    read -rp "  API key: " OPENAI_API_KEY
    [[ -z "$OPENAI_API_KEY" ]] && { err "API key is required."; exit 1; }
    read -rp "  Context window tokens (default: 16384): " LLM_CTX
    LLM_CTX="${LLM_CTX:-16384}"
    ;;
  *) err "Invalid choice"; exit 1 ;;
esac

# ── Other settings ────────────────────────────────────────────────────────────
header "General settings"
read -rp "  Frontend port (default: 3000): " FRONTEND_PORT
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
read -rp "  Concurrent research workers (default: 4): " WORKER_THREADS
WORKER_THREADS="${WORKER_THREADS:-4}"

# ── Write .env ────────────────────────────────────────────────────────────────
header "Writing .env"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cat > "${SCRIPT_DIR}/.env" << ENVEOF
# Generated by install.sh on $(date)

LLM_PROVIDER=${LLM_PROVIDER}
LLM_MODEL=${LLM_MODEL}
LLM_CTX=${LLM_CTX}

OLLAMA_HOST=${OLLAMA_HOST}
OLLAMA_BASE_URL=${OLLAMA_BASE_URL}
OLLAMA_API_KEY=${OLLAMA_API_KEY}

OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_BASE_URL=${OPENAI_BASE_URL}

FRONTEND_PORT=${FRONTEND_PORT}
WORKER_THREADS=${WORKER_THREADS}
AI_QUERY_MAX_LENGTH=5000
AI_REQUEST_TIMEOUT=14400
ALLOWED_ORIGINS=*
MEMORY_DIR=/data/memory
DATA_DIR=/data
ENVEOF

info ".env written to ${SCRIPT_DIR}/.env"

# ── Build and launch ──────────────────────────────────────────────────────────
header "Starting EvidionAI"
echo "  Building Docker images (first run may take a few minutes)…"
$COMPOSE_CMD -f "${SCRIPT_DIR}/docker-compose.yml" up --build -d

echo ""
info "EvidionAI is up!"
echo ""
echo -e "  ${BOLD}Browser:${RESET}   http://localhost:${FRONTEND_PORT}"
echo -e "  ${BOLD}API docs:${RESET}  http://localhost:${FRONTEND_PORT}/api/docs"
echo ""
echo "  Logs:  $COMPOSE_CMD logs -f"
echo "  Stop:  $COMPOSE_CMD down"
echo ""
echo -e "${CYAN}${BOLD}Happy researching! 🔬${RESET}"
