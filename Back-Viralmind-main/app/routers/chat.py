import httpx

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import ChatHistory, User
from app.schemas import ChatRequest, ChatResponse

router = APIRouter()


async def ask_gemini(message: str) -> str:
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY não configurada no arquivo .env.",
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
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                url,
                json=body,
                headers={
                    "x-goog-api-key": settings.gemini_api_key,
                    "Content-Type": "application/json",
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Não foi possível conectar à Gemini.",
        ) from exc

    if response.status_code != 200:
        try:
            error_data = response.json()
            error_message = error_data.get("error", {}).get(
                "message",
                "A Gemini recusou a solicitação.",
            )
        except Exception:
            error_message = response.text or "A Gemini recusou a solicitação."

        raise HTTPException(
            status_code=502,
            detail=f"Gemini: {error_message}",
        )

    try:
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise HTTPException(
            status_code=502,
            detail="A Gemini retornou uma resposta inválida.",
        )


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
