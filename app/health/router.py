from fastapi import APIRouter, Request

from app.models import HealthResponse, OllamaCheck

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    ollama_ok = await request.app.state.ollama_client.is_available()
    return HealthResponse(
        status="ok" if ollama_ok else "degraded",
        checks=OllamaCheck(available=ollama_ok),
    )
