# app/routers/chat.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from groq import Groq
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import ChatHistory, User
from app.schemas import ChatHistoryItem, ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter()


async def ask_groq(message: str, previous_messages: list[dict] | None = None) -> str:
    if not settings.groq_api_key:
        logger.error("GROQ_API_KEY não configurada no ambiente.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuração do servidor incompleta: GROQ_API_KEY ausente.",
        )

    system_prompt = (
        "Você é o assistente de IA do ViralMind, especialista em crescimento no YouTube e redes sociais. "
        "Ajude criadores de conteúdo com ideias de vídeos virais, títulos altamente clicáveis, ganchos (hooks) magnéticos, "
        "roteiros envolventes, SEO, retenção de audiência e estratégias de monetização. "
        "Responda sempre em português do Brasil de forma dinâmica, estruturada, prática e amigável."
    )

    messages_payload = [{"role": "system", "content": system_prompt}]

    if previous_messages:
        messages_payload.extend(previous_messages)

    messages_payload.append({"role": "user", "content": message})

    try:
        client = Groq(api_key=settings.groq_api_key)
        completion = client.chat.completions.create(
            model=settings.groq_model,
            messages=messages_payload,
            temperature=0.8,
            max_completion_tokens=2048,
            top_p=1,
            stream=False,
        )

        return completion.choices[0].message.content or ""

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
    previous_messages = []
    if data.include_history:
        # Busca as últimas 6 mensagens para manter a memória contínua do chat
        recent_chats = (
            db.query(ChatHistory)
            .filter(ChatHistory.user_id == user.id)
            .order_by(ChatHistory.created_at.desc())
            .limit(6)
            .all()
        )
        for ch in reversed(recent_chats):
            previous_messages.append({"role": "user", "content": ch.message})
            previous_messages.append({"role": "assistant", "content": ch.response})

    response = await ask_groq(data.message, previous_messages)

    history = ChatHistory(
        user_id=user.id,
        message=data.message,
        response=response,
    )
    db.add(history)
    db.commit()

    return ChatResponse(response=response)


@router.get("/history", response_model=list[ChatHistoryItem])
def get_chat_history(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retorna o histórico de conversas do usuário logado de forma dinâmica.
    """
    histories = (
        db.query(ChatHistory)
        .filter(ChatHistory.user_id == user.id)
        .order_by(ChatHistory.created_at.asc())
        .limit(limit)
        .all()
    )
    return histories


@router.delete("/history", status_code=status.HTTP_200_OK)
def clear_chat_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Limpa o histórico de chat do usuário.
    """
    db.query(ChatHistory).filter(ChatHistory.user_id == user.id).delete()
    db.commit()
    return {"message": "Histórico de conversas limpo com sucesso."}

