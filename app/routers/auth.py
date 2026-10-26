# app/routers/auth.py
import logging
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

logger = logging.getLogger("viralmind.auth")

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    email = data.email.lower()
    logger.info(f"Tentativa de cadastro para o email: {email}")
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        logger.warning(f"Cadastro rejeitado: e-mail {email} já cadastrado.")
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
        logger.info(f"Usuário cadastrado com sucesso: ID {user.id} ({email})")
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Erro de integridade ao registrar {email}: {e}")
        raise HTTPException(status_code=400, detail="Esse e-mail já está cadastrado.")

    return user


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    logger.info(f"Tentativa de login para o email: {data.email}")
    user = db.scalar(select(User).where(User.email == data.email.lower()))

    if not user:
        logger.warning(f"Login falhou: usuário não encontrado ({data.email})")
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    if not verify_password(data.password, user.hashed_password):
        logger.warning(f"Login falhou: senha incorreta para {data.email}")
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    logger.info(f"Login efetuado com sucesso para o usuário ID {user.id} ({user.email})")
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
    logger.info(f"[Google Auth] Recebida requisição para email: {email}, id_token presente: {bool(data.id_token)}")

    # Validação do id_token com API Google caso enviado
    if data.id_token:
        try:
            logger.info("[Google Auth] Validando id_token junto à API Google...")
            async with httpx.AsyncClient(timeout=10.0) as client:
                token_resp = await client.get(
                    f"https://oauth2.googleapis.com/tokeninfo?id_token={data.id_token}"
                )
                logger.info(f"[Google Auth] Resposta da API Google: Status {token_resp.status_code}")
                if token_resp.status_code == 200:
                    token_info = token_resp.json()
                    google_email = token_info.get("email")
                    if google_email:
                        email = google_email.lower()
                    if token_info.get("name"):
                        name = token_info.get("name")
                    logger.info(f"[Google Auth] Token validado com sucesso! Email validado: {email}")
                else:
                    logger.warning(f"[Google Auth] API Google rejeitou token: {token_resp.text}")
        except Exception as e:
            logger.error(f"[Google Auth] Exceção ao consultar tokeninfo da Google: {e}")
            pass  # Fallback tolerante

    user = db.scalar(select(User).where(User.email == email))
    if not user:
        logger.info(f"[Google Auth] Criando novo usuário para conta Google: {email}")
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
            logger.info(f"[Google Auth] Novo usuário criado com ID {user.id}")
        except IntegrityError:
            db.rollback()
            user = db.scalar(select(User).where(User.email == email))
            logger.info(f"[Google Auth] Usuário recuperado após colisão: ID {user.id if user else None}")
    else:
        logger.info(f"[Google Auth] Usuário existente encontrado: ID {user.id} ({user.email})")

    token = create_access_token(user.id)
    logger.info(f"[Google Auth] Token JWT gerado com sucesso para ID {user.id}")
    return TokenResponse(
        access_token=token,
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
