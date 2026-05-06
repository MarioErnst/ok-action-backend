from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import get_session
from app.presentation.schemas.auth import LoginRequest, LoginResponse, RegisterRequest, SocialLoginRequest
from app.use_cases.auth.login import login_user
from app.use_cases.auth.register import register_user
from app.use_cases.auth.social_login import social_login_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, session: AsyncSession = Depends(get_session)):
    result = await login_user(request.email, request.password, session)

    if not result:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_credentials",
                "message": "Credenciales inválidas",
            },
        )

    return result


@router.post("/register", response_model=LoginResponse)
async def register(request: RegisterRequest, session: AsyncSession = Depends(get_session)):
    result = await register_user(request.email, request.password, request.full_name, session)

    if not result:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "email_already_registered",
                "message": "El correo electrónico ya está registrado",
            },
        )

    return result


@router.post("/social-login", response_model=LoginResponse)
async def social_login(request: SocialLoginRequest, session: AsyncSession = Depends(get_session)):
    # Here you would typically validate request.token with the provider
    # For now we assume the frontend sends a valid token and verified email/name
    
    result = await social_login_user(request.email, request.full_name, request.provider, session)

    if not result:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "authentication_failed",
                "message": "Fallo la autenticación social",
            },
        )

    return result
