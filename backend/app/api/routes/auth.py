from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.api.deps import get_current_user, get_session_user
from app.models import User
from app.models.user import USER_ACTIVE
from app.schemas.auth import LoginRequest, UserOut
from app.schemas.users import PasswordChangeIn, RegisterIn, RegisterOut
from app.security import create_session_token, verify_password
from app.services.users import STATUS_ERRORS, UserError, change_password, find_by_login, register_user

router = APIRouter()


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await find_by_login(session, body.username)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )
    if user.status != USER_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=STATUS_ERRORS.get(user.status, "Вход недоступен"),
        )
    _set_session_cookie(response, create_session_token(user.id))
    return user


@router.post("/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterIn,
    session: AsyncSession = Depends(get_session),
) -> RegisterOut:
    try:
        user = await register_user(session, body)
    except UserError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return RegisterOut(status=user.status)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def update_password(
    body: PasswordChangeIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await change_password(session, user, body.current_password, body.new_password)
    except UserError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        samesite="lax",
        secure=settings.cookie_secure,
        httponly=True,
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_session_user)) -> User:
    return user
