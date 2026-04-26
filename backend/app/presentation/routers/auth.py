from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import get_session
from app.presentation.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
)
from app.use_cases.auth.login import login_user
from app.use_cases.auth.register import register_user

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


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(request: RegisterRequest, session: AsyncSession = Depends(get_session)):
    result = await register_user(
        full_name=request.full_name,
        email=request.email,
        password=request.password,
        session=session,
    )

    if not result:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "email_already_registered",
                "message": "El correo ya esta registrado",
            },
        )

    return result
