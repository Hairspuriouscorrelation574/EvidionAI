import os

base_url = os.getenv("AI_AGENTS_HOST", "ai_agents_service")
port     = int(os.getenv("AI_AGENTS_PORT", "8000"))
