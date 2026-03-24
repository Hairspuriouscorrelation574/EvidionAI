FROM python:3.11-slim

WORKDIR /app

# System deps for chromadb + sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY ai_agents_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ai_agents_service/ .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
