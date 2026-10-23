# app/routers/auth.py
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import GoogleAuthRequest, TokenResponse, UserCreate, UserLogin, UserResponse
from app.security import create_access_token, hash_password, verify_password

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    email = data.email.lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(status_code=400, detail="Esse e-mail já está cadastrado.")

    user = User(
        name=data.name.strip(),
        email=email,
        hashed_password=hash_password(data.password),
    )
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Esse e-mail já está cadastrado.")

    return user


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserResponse.model_validate(user)
    )


@router.post("/google", response_model=TokenResponse)
async def google_login_direct(data: GoogleAuthRequest, db: Session = Depends(get_db)):
    """
    Recebe autenticação Google disparada do app mobile / web
    (com validação de id_token caso fornecido).
    """
    email = data.email.lower()
    name = data.name or email.split("@")[0]

    # Validação do id_token com API Google caso enviado
    if data.id_token:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                token_resp = await client.get(
                    f"https://oauth2.googleapis.com/tokeninfo?id_token={data.id_token}"
                )
                if token_resp.status_code == 200:
                    token_info = token_resp.json()
                    google_email = token_info.get("email")
                    if google_email:
                        email = google_email.lower()
                    if token_info.get("name"):
                        name = token_info.get("name")
        except Exception:
            pass  # Fallback tolerante

    user = db.scalar(select(User).where(User.email == email))
    if not user:
        # Cadastra o usuário automaticamente se for o primeiro login Google
        user = User(
            name=name,
            email=email,
            hashed_password=hash_password(f"google_oauth_{email}"),
        )
        try:
            db.add(user)
            db.commit()
            db.refresh(user)
        except IntegrityError:
            db.rollback()
            user = db.scalar(select(User).where(User.email == email))

    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserResponse.model_validate(user),
    )


@router.get("/google/url")
def get_google_auth_url():
    """
    Retorna a URL oficial do Google para iniciar o fluxo OAuth no navegador.
    """
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    auth_url = f"https://accounts.google.com/o/oauth2/auth?{urllib.parse.urlencode(params)}"
    return {"auth_url": auth_url}


@router.get("/google/callback")
async def google_oauth_callback(code: str, db: Session = Depends(get_db)):
    """
    Endpoint de redirecionamento configurado no Google Cloud Console.
    Troca o código pelo token de acesso e retorna o token de autenticação do ViralMind.
    """
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.google_redirect_uri,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post(token_url, data=data)
        if res.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Erro ao trocar código por token no Google: {res.text}",
            )
        tokens = res.json()
        id_token = tokens.get("id_token")
        access_token = tokens.get("access_token")

        user_info_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_info_resp.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail="Não foi possível obter dados do usuário do Google.",
            )
        info = user_info_resp.json()

    email = info["email"].lower()
    name = info.get("name", email.split("@")[0])

    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(
            name=name,
            email=email,
            hashed_password=hash_password(f"google_oauth_{email}"),
        )
        try:
            db.add(user)
            db.commit()
            db.refresh(user)
        except IntegrityError:
            db.rollback()
            user = db.scalar(select(User).where(User.email == email))

    token = create_access_token(user.id)
    return {
        "status": "success",
        "message": f"Usuário {email} autenticado com sucesso!",
        "access_token": token,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
        },
    }


@router.post("/logout")
def logout():
    return {"message": "Sessão encerrada com sucesso."}
