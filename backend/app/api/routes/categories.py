from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_session
from app.models import User
from app.schemas.category import AssignmentIn, CategoriesOut, CategoryCreate, CategoryPatch
from app.services.categories import (
    CategoryError,
    assign_holding,
    create_category,
    delete_category,
    list_categories,
    patch_category,
)

router = APIRouter()


def _http(exc: CategoryError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("", response_model=CategoriesOut)
async def get_categories(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CategoriesOut:
    return await list_categories(session, user)


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_category(
    body: CategoryCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        category = await create_category(session, user, body)
    except CategoryError as exc:
        raise _http(exc) from exc
    return {"id": category.id, "name": category.name, "parent_id": category.parent_id}


@router.patch("/{category_id}")
async def update_category(
    category_id: int,
    body: CategoryPatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        category = await patch_category(session, user, category_id, body)
    except CategoryError as exc:
        raise _http(exc) from exc
    return {"id": category.id, "name": category.name, "parent_id": category.parent_id}


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_category(
    category_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await delete_category(session, user, category_id)
    except CategoryError as exc:
        raise _http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/assignments", status_code=status.HTTP_204_NO_CONTENT)
async def put_assignment(
    body: AssignmentIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await assign_holding(session, user, body)
    except CategoryError as exc:
        raise _http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
