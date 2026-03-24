from fastapi import APIRouter

router = APIRouter()

@router.get("/ping", summary="Ping")
async def ping():
    return {"pong": True}
