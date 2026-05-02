"""Auth endpoints: register, login, refresh, logout, password reset."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.auth_service import (
    register, login, refresh, logout,
    request_password_reset, reset_password, TokenPair,
)
from app.middleware.auth import get_current_user
from app.models.auth import User

router = APIRouter(tags=["auth"])
auth_router = router  # alias for importability


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ResetRequestBody(BaseModel):
    email: str


class ResetConfirmBody(BaseModel):
    token: str
    new_password: str


@router.post("/register", response_model=TokenPair, status_code=201)
def auth_register(body: RegisterRequest, db: Session = Depends(get_db)):
    return register(body.email, body.password, body.display_name, db)


@router.post("/login", response_model=TokenPair)
def auth_login(body: LoginRequest, db: Session = Depends(get_db)):
    return login(body.email, body.password, db)


@router.post("/refresh", response_model=TokenPair)
def auth_refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    return refresh(body.refresh_token, db)


@router.post("/logout", status_code=204)
def auth_logout(
    body: LogoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logout(current_user.id, body.refresh_token, db)


@router.post("/reset-password/request", status_code=204)
def auth_reset_request(body: ResetRequestBody, db: Session = Depends(get_db)):
    request_password_reset(body.email, db)


@router.post("/reset-password/confirm", status_code=204)
def auth_reset_confirm(body: ResetConfirmBody, db: Session = Depends(get_db)):
    reset_password(body.token, body.new_password, db)


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "display_name": current_user.display_name,
        "role": current_user.role,
        "plan": current_user.plan,
    }
