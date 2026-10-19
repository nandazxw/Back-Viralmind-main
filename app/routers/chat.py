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

    client = Groq(api_key=settings.groq_api_key)

    # Lista de modelos prioritários caso o modelo principal sofra rate limit (413/429)
    models_to_try = [settings.groq_model]
    for fallback_model in ["openai/gpt-oss-20b", "qwen/qwen3.8-27b"]:
        if fallback_model not in models_to_try:
            models_to_try.append(fallback_model)

    last_exception = None
    for model_name in models_to_try:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=messages_payload,
                temperature=0.8,
                max_completion_tokens=1024,
                top_p=1,
                stream=False,
            )
            return completion.choices[0].message.content or ""
        except Exception as exc:
            last_exception = exc
            error_msg = str(exc)
            # Se for estouro de tokens ou rate limit, tenta o próximo modelo disponível
            if "413" in error_msg or "rate_limit" in error_msg or "tokens" in error_msg:
                logger.warning(
                    f"Limite de tokens atingido para o modelo '{model_name}'. Tentando modelo alternativo... Erro: {exc}"
                )
                continue
            logger.error(f"Erro ao acessar a API do Groq com {model_name}: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Serviço Groq com instabilidade ou falha: {exc}",
            ) from exc

    logger.error(f"Todos os modelos da Groq falharam por limite de tokens: {last_exception}")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Serviço Groq excedeu o limite de tokens da conta: {last_exception}",
    )


@router.post("/", response_model=ChatResponse)
async def chat(
    data: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    previous_messages = []
    if data.include_history:
        # Busca as últimas 4 mensagens e limita caracteres para proteger o limite de TPM da Groq
        recent_chats = (
            db.query(ChatHistory)
            .filter(ChatHistory.user_id == user.id)
            .order_by(ChatHistory.created_at.desc())
            .limit(4)
            .all()
        )
        for ch in reversed(recent_chats):
            # Limita a resposta histórica anterior a no máximo 1000 caracteres para não inflar o payload
            user_msg = ch.message[:500] if len(ch.message) > 500 else ch.message
            assistant_msg = ch.response[:1000] if len(ch.response) > 1000 else ch.response
            previous_messages.append({"role": "user", "content": user_msg})
            previous_messages.append({"role": "assistant", "content": assistant_msg})

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

