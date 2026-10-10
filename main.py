from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import Base, engine, SessionLocal
from app import models
from app.routers import auth, chat, users, schedule
from app.dependencies import get_current_user
from app.schemas import UserResponse

# 1. Cria as tabelas do banco automaticamente
Base.metadata.create_all(bind=engine)

# 2. Worker em segundo plano (APScheduler)
def check_schedules_job():
    db = SessionLocal()
    try:
        now = datetime.now()
        pending_items = db.query(models.Schedule).filter(
            models.Schedule.status == "pending",
            models.Schedule.scheduled_time <= now
        ).all()

        for item in pending_items:
            print(f"🚨 [NOTIFICAÇÃO DISPARADA] Usuário: {item.user_id} | Horário: {item.scheduled_time.strftime('%H:%M')}")
            item.status = "sent"

        db.commit()
    except Exception as e:
        print(f"Erro no worker de agendamento: {e}")
        db.rollback()
    finally:
        db.close()

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(check_schedules_job, 'interval', seconds=30)
    scheduler.start()
    yield
    scheduler.shutdown()

# 3. Inicialização da aplicação
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="API do ViralMind para criadores de conteúdo no YouTube.",
    lifespan=lifespan
)

# 4. Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 5. Registro de Roteadores (Com suporte a chamadas com e sem o prefixo /api)
app.include_router(auth.router, prefix="/auth", tags=["Autenticação"])
app.include_router(auth.router, prefix="/api/auth", tags=["Autenticação"])

app.include_router(users.router, prefix="/users", tags=["Usuários"])
app.include_router(users.router, prefix="/api/users", tags=["Usuários"])

app.include_router(chat.router, prefix="/chat", tags=["Chat IA"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat IA"])

app.include_router(schedule.router, prefix="/schedule", tags=["Agendamento"])
app.include_router(schedule.router, prefix="/api/schedule", tags=["Agendamento"])


@app.get("/")
def home():
    return {
        "nome": "ViralMind API",
        "status": "online",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me", response_model=UserResponse)
def get_current_user_me(user: models.User = Depends(get_current_user)):
    """
    Retorna os dados do usuário logado atualmente direto na raiz.
    """
    return user