# app/routers/chat.py
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import ChatHistory, User
from app.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter()


async def ask_gemini(message: str) -> str:
    if not settings.gemini_api_key:
        logger.error("GEMINI_API_KEY não configurada no ambiente.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuração do servidor incompleta: GEMINI_API_KEY ausente.",
        )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )

    prompt = (
        "Você é o assistente de IA do ViralMind. "
        "Ajude criadores de conteúdo do YouTube com ideias de vídeos, "
        "títulos, ganchos, roteiros, SEO, retenção e estratégias de crescimento. "
        "Responda em português do Brasil de forma natural, prática e objetiva.\n\n"
        f"Mensagem do criador: {message}"
    )

    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt,
                    }
                ]
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                json=body,
                headers={
                    "x-goog-api-key": settings.gemini_api_key,
                    "Content-Type": "application/json",
                },
            )
    except httpx.RequestError as exc:
        logger.error(f"Erro de conexão ao acessar a API do Gemini: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de IA temporariamente indisponível. Não foi possível conectar ao Gemini.",
        ) from exc

    if response.status_code != 200:
        error_detail = "Erro desconhecido retornado pela API do Gemini."
        try:
            error_data = response.json()
            error_detail = error_data.get("error", {}).get("message", response.text)
        except Exception:
            error_detail = response.text or error_detail

        logger.error(f"Gemini API Error [{response.status_code}]: {error_detail}")

        # Se for erro de cliente (400, 401, 403, 404, 429), repassa o status correspondente
        if 400 <= response.status_code < 500:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Falha na requisição ao Gemini: {error_detail}",
            )

        # Se o Google respondeu 5xx, devolve 503
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Serviço Gemini com instabilidade: {error_detail}",
        )

    try:
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.error(f"Resposta inesperada do Gemini: {response.text}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Resposta inesperada recebida da API de IA.",
        ) from exc


@router.post("/", response_model=ChatResponse)
async def chat(
    data: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response = await ask_gemini(data.message)

    history = ChatHistory(
        user_id=user.id,
        message=data.message,
        response=response,
    )
    db.add(history)
    db.commit()

    return ChatResponse(response=response)
