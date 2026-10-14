# app/routers/chat.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from groq import Groq
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import ChatHistory, User
from app.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter()


async def ask_groq(message: str) -> str:
    if not settings.groq_api_key:
        logger.error("GROQ_API_KEY não configurada no ambiente.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuração do servidor incompleta: GROQ_API_KEY ausente.",
        )

    prompt = (
        "Você é o assistente de IA do ViralMind. "
        "Ajude criadores de conteúdo do YouTube com ideias de vídeos, "
        "títulos, ganchos, roteiros, SEO, retenção e estratégias de crescimento. "
        "Responda em português do Brasil de forma natural, prática e objetiva.\n\n"
        f"Mensagem do criador: {message}"
    )

    try:
        client = Groq(api_key=settings.groq_api_key)
        completion = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=1,
            max_completion_tokens=2048,
            top_p=1,
            reasoning_effort="medium",
            stream=True,
            stop=None,
        )

        response_chunks = []
        for chunk in completion:
            content = chunk.choices[0].delta.content or ""
            print(content, end="")
            response_chunks.append(content)

        return "".join(response_chunks)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Erro ao acessar a API do Groq: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Serviço Groq com instabilidade ou falha: {exc}",
        ) from exc


@router.post("/", response_model=ChatResponse)
async def chat(
    data: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response = await ask_groq(data.message)

    history = ChatHistory(
        user_id=user.id,
        message=data.message,
        response=response,
    )
    db.add(history)
    db.commit()

    return ChatResponse(response=response)
