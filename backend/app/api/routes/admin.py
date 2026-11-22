from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db import get_session
from app.models import User
from app.schemas.users import (
    AdminUsersOut,
    BulkActionIn,
    BulkActionOut,
    LegacyPortfolioOut,
    TransferIn,
    UserStatus,
)
from app.services.users import (
    UserError,
    apply_action,
    legacy_portfolio,
    list_users,
    transfer_legacy_portfolio,
)

router = APIRouter()


@router.get("/users", response_model=AdminUsersOut)
async def get_users(
    statuses: list[UserStatus] = Query(default=[], alias="status"),
    q: str = Query(default="", max_length=128),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUsersOut:
    return await list_users(session, list(statuses), q)


@router.post("/users/actions", response_model=BulkActionOut)
async def post_users_action(
    body: BulkActionIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> BulkActionOut:
    return await apply_action(session, admin, body.ids, body.action)


@router.get("/legacy-portfolio", response_model=LegacyPortfolioOut)
async def get_legacy_portfolio(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> LegacyPortfolioOut:
    return await legacy_portfolio(session, admin)


@router.post("/legacy-portfolio/transfer", status_code=status.HTTP_204_NO_CONTENT)
async def post_transfer_legacy_portfolio(
    body: TransferIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await transfer_legacy_portfolio(session, admin, body.user_id)
    except UserError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
