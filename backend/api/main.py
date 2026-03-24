import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db.database import init_db
from routes.ai_agents_api.routes import router as ai_router
from routes.chats.routes import router as chats_router
from routes.projects.routes import router as projects_router
from routes.utils.routes import router as utils_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("api_gateway")

_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]

app = FastAPI(
    title="EvidionAI API",
    description=(
        "REST + SSE API for the EvidionAI multi-agent research system.\n\n"
        "All endpoints are open — no authentication required.\n"
        "Deploy behind a firewall or reverse-proxy for access control."
    ),
    version="1.0.0",
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.on_event("startup")
def startup():
    init_db()
    log.info("SQLite database initialised")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("Unhandled error %s %s: %s", request.method, request.url, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health", tags=["System"], summary="Health check")
async def health():
    return {"status": "ok"}


app.include_router(ai_router, tags=["AI Agents"], prefix="/ai")
app.include_router(chats_router, tags=["Chats"], prefix="/chats")
app.include_router(projects_router, tags=["Projects"], prefix="/projects")
app.include_router(utils_router, tags=["Utils"], prefix="/utils")
