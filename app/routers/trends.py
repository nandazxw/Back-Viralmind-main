# app/routers/trends.py
import json
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from groq import Groq
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Trend, User
from app.schemas import TrendGenerateRequest, TrendItem

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="",
    tags=["Trends"]
)

# Base de fallback dinâmica caso a chave de IA não esteja acessível temporariamente
DEFAULT_TRENDS = [
    {
        "niche": "Tecnologia",
        "title": "A Nova Era dos Agentes de IA Autônomos",
        "description": "Como modelos locais e agentes estão automatizando rotinas completas de desenvolvimento e trabalho.",
        "category": "Inteligência Artificial",
        "growth_score": 97,
        "suggested_hook": "Você ainda está programando linha por linha? Em 2026 isso mudou para sempre.",
        "suggested_tags": "#ia, #tecnologia, #programacao, #produtividade"
    },
    {
        "niche": "Finanças",
        "title": "O Fim dos Investimentos Tradicionais para Iniciantes",
        "description": "Análise de estratégias que os criadores de conteúdo financeiro estão usando para atrair retenção máxima.",
        "category": "Investimentos",
        "growth_score": 92,
        "suggested_hook": "Se você guardar seu dinheiro na poupança este ano, você está literalmente perdendo poder de compra todo mês.",
        "suggested_tags": "#financas, #investimentos, #rendapassiva, #dinheiro"
    },
    {
        "niche": "Gamer",
        "title": "Os 5 Jogos Mais Esperados e Segredos Ocultos nos Trailers",
        "description": "Roteiro dinâmico com cortes rápidos e análise quadro a quadro.",
        "category": "Games",
        "growth_score": 89,
        "suggested_hook": "Quase ninguém percebeu esse easter egg aos 42 segundos deste trailer...",
        "suggested_tags": "#games, #gaming, #easteregg, #noticias"
    },
    {
        "niche": "Marketing Digital",
        "title": "Estratégia dos Primeiros 3 Segundos no YouTube Shorts e Reels",
        "description": "Métricas reais de retenção que destravam o algoritmo.",
        "category": "Crescimento Orgânico",
        "growth_score": 95,
        "suggested_hook": "Pare de se apresentar no início dos seus vídeos se quiser visualizações.",
        "suggested_tags": "#viral, #marketingdigital, #shorts, #reels"
    }
]


def generate_trends_with_ai(niche: str, count: int = 5) -> list[dict]:
    """
    Gera tendências e ideias de vídeos altamente virais em tempo real usando a Groq.
    """
    if not settings.groq_api_key:
        return [t for t in DEFAULT_TRENDS if niche.lower() in t["niche"].lower()] or DEFAULT_TRENDS[:count]

    prompt = f"""
    Você é um analista sênior de tendências de conteúdo viral para YouTube, TikTok e Reels.
    Gere exatamente {count} ideias de temas quentes / tendências em alta (trends) para o nicho: "{niche}".
    
    Retorne estritamente um array JSON válido, sem texto explicativo antes ou depois, seguindo este formato exato:
    [
      {{
        "title": "Título magnético e viral da tendência",
        "description": "Breve explicação do porquê esse tema está explodindo e como abordar",
        "category": "Categoria ou subtópico",
        "growth_score": 94,
        "suggested_hook": "Gancho de abertura poderoso nos primeiros 3 segundos do vídeo",
        "suggested_tags": "#tag1, #tag2, #tag3"
      }}
    ]
    """

    try:
        client = Groq(api_key=settings.groq_api_key)
        completion = client.chat.completions.create(
            model=settings.groq_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_completion_tokens=1500,
        )
        content = completion.choices[0].message.content.strip()
        # Tratamento caso o modelo envolva em blocos de markdown ```json
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        
        parsed = json.loads(content)
        for item in parsed:
            item["niche"] = niche
        return parsed
    except Exception as exc:
        logger.warning(f"Falha ao gerar trends via IA ({exc}), aplicando tendências padrão.")
        return [
            {
                "niche": niche,
                "title": f"Tendência em Alta no Nicho de {niche}",
                "description": f"Ideia emergente para impulsionar canais de {niche} esta semana.",
                "category": niche,
                "growth_score": 90,
                "suggested_hook": f"Se você cria conteúdo sobre {niche}, precisa saber disso agora.",
                "suggested_tags": f"#{niche.lower().replace(' ', '')}, #viral, #tendencia"
            }
        ]


@router.get("/", response_model=list[TrendItem])
def get_trends(
    niche: str | None = Query(None, description="Filtrar tendências por nicho"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Retorna as tendências armazenadas no banco de dados. Caso o banco esteja vazio para o nicho,
    popula automaticamente de forma dinâmica.
    """
    query = db.query(Trend)
    if niche:
        query = query.filter(Trend.niche.ilike(f"%{niche}%"))

    trends = query.order_by(Trend.growth_score.desc()).limit(limit).all()

    if not trends:
        # Se ainda não existem trends no banco para este nicho, gera dinamicamente
        search_niche = niche if niche else "Geral"
        generated = generate_trends_with_ai(search_niche, count=min(limit, 5))
        trends = []
        for g in generated:
            item = Trend(
                niche=g.get("niche", search_niche),
                title=g.get("title", ""),
                description=g.get("description", ""),
                category=g.get("category", search_niche),
                growth_score=g.get("growth_score", 85),
                suggested_hook=g.get("suggested_hook", ""),
                suggested_tags=g.get("suggested_tags", ""),
            )
            db.add(item)
            trends.append(item)
        db.commit()
        for item in trends:
            db.refresh(item)

    return trends


@router.post("/generate", response_model=list[TrendItem], status_code=status.HTTP_201_CREATED)
def generate_trends(
    data: TrendGenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Gera novas tendências sob demanda com IA para um nicho específico e persiste no banco de dados.
    """
    generated = generate_trends_with_ai(data.niche, count=data.count)
    saved_items = []
    for g in generated:
        item = Trend(
            niche=g.get("niche", data.niche),
            title=g.get("title", ""),
            description=g.get("description", ""),
            category=g.get("category", data.niche),
            growth_score=g.get("growth_score", 85),
            suggested_hook=g.get("suggested_hook", ""),
            suggested_tags=g.get("suggested_tags", ""),
        )
        db.add(item)
        saved_items.append(item)

    db.commit()
    for item in saved_items:
        db.refresh(item)

    return saved_items
