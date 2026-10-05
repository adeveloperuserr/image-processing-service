from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_settings
from app.models import User
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserSummary
from app.security import create_access_token, hash_password, verify_password
from app.settings import Settings

router = APIRouter(prefix="/auth", tags=["autenticación"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def _token_response(user: User, settings: Settings) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, settings),
        user=UserSummary(id=user.id, email=user.email),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    db: DatabaseSession,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    email = str(payload.email).strip().lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo.")

    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Ya existe una cuenta con ese correo."
        ) from error
    db.refresh(user)
    return _token_response(user, settings)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    db: DatabaseSession,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    email = str(payload.email).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El correo o la contraseña no coinciden.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _token_response(user, settings)
