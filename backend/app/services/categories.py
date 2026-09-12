from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, HoldingCategory, User
from app.schemas.category import (
    AssignmentIn,
    CategoriesOut,
    CategoryCreate,
    CategoryHoldingOut,
    CategoryNodeOut,
    CategoryPatch,
)
from app.services.portfolio import build_dashboard, money_str

ZERO = Decimal("0")
HUNDRED = Decimal("100")
MAX_DEPTH = 8


class CategoryError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def list_categories(session: AsyncSession, user: User) -> CategoriesOut:
    categories = await _user_categories(session, user.id)
    assignments = await _assignments(session, [item.id for item in categories])
    dashboard = await build_dashboard(session, user)
    values, meta = _position_index(dashboard.positions)
    portfolio_value = Decimal(dashboard.value)

    holdings_by_cat: dict[int, list[CategoryHoldingOut]] = defaultdict(list)
    assigned_figis: set[str] = set()
    own_value: dict[int, Decimal] = {item.id: ZERO for item in categories}
    for row in assignments:
        assigned_figis.add(row.figi)
        info = meta.get(row.figi, {"ticker": row.figi, "name": row.figi, "is_cash": False})
        amount = values.get(row.figi, ZERO)
        own_value[row.category_id] = own_value.get(row.category_id, ZERO) + amount
        holdings_by_cat[row.category_id].append(
            CategoryHoldingOut(
                figi=row.figi,
                ticker=info["ticker"],
                name=info["name"],
                value=money_str(amount),
                is_cash=bool(info["is_cash"]),
            )
        )

    children_map: dict[int | None, list[Category]] = defaultdict(list)
    for item in categories:
        children_map[item.parent_id].append(item)
    for group in children_map.values():
        group.sort(key=lambda item: (item.sort_order, item.id))

    total_by_id: dict[int, Decimal] = {}

    def rollup(node: Category) -> Decimal:
        total = own_value.get(node.id, ZERO)
        for child in children_map.get(node.id, []):
            total += rollup(child)
        total_by_id[node.id] = total
        return total

    roots = children_map.get(None, [])
    for root in roots:
        rollup(root)

    def to_node(node: Category) -> CategoryNodeOut:
        total = total_by_id.get(node.id, ZERO)
        target = node.target_share or ZERO
        fact = (total / portfolio_value * HUNDRED) if portfolio_value > 0 else ZERO
        return CategoryNodeOut(
            id=node.id,
            parent_id=node.parent_id,
            name=node.name,
            target_share=money_str(target),
            sort_order=node.sort_order,
            value=money_str(total),
            own_value=money_str(own_value.get(node.id, ZERO)),
            fact_share=money_str(fact),
            delta_share=money_str(fact - target),
            holdings=holdings_by_cat.get(node.id, []),
            children=[to_node(child) for child in children_map.get(node.id, [])],
        )

    unassigned_value = ZERO
    unassigned: list[CategoryHoldingOut] = []
    for figi, info in sorted(meta.items(), key=lambda item: (-values.get(item[0], ZERO), item[1]["ticker"])):
        if figi in assigned_figis:
            continue
        amount = values.get(figi, ZERO)
        unassigned_value += amount
        unassigned.append(
            CategoryHoldingOut(
                figi=figi,
                ticker=info["ticker"],
                name=info["name"],
                value=money_str(amount),
                is_cash=bool(info["is_cash"]),
            )
        )

    root_target = sum((item.target_share or ZERO for item in roots), ZERO)
    unassigned_share = (unassigned_value / portfolio_value * HUNDRED) if portfolio_value > 0 else ZERO
    return CategoriesOut(
        tree=[to_node(item) for item in roots],
        unassigned=unassigned,
        portfolio_value=money_str(portfolio_value),
        root_target=money_str(root_target),
        unassigned_value=money_str(unassigned_value),
        unassigned_share=money_str(unassigned_share),
    )


async def create_category(session: AsyncSession, user: User, body: CategoryCreate) -> Category:
    name = body.name.strip()
    if not name:
        raise CategoryError("Название не может быть пустым")
    parent = None
    if body.parent_id is not None:
        parent = await _owned_category(session, user.id, body.parent_id)
        if await _depth(session, parent) >= MAX_DEPTH:
            raise CategoryError("Слишком глубокое дерево папок")
    sort_order = await _next_sort(session, user.id, body.parent_id)
    category = Category(
        user_id=user.id,
        parent_id=body.parent_id,
        name=name,
        target_share=body.target_share,
        sort_order=sort_order,
    )
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


async def patch_category(
    session: AsyncSession, user: User, category_id: int, body: CategoryPatch
) -> Category:
    category = await _owned_category(session, user.id, category_id)
    if "name" in body.model_fields_set and body.name is not None:
        name = body.name.strip()
        if not name:
            raise CategoryError("Название не может быть пустым")
        category.name = name
    if "target_share" in body.model_fields_set and body.target_share is not None:
        category.target_share = body.target_share
    if "sort_order" in body.model_fields_set and body.sort_order is not None:
        category.sort_order = body.sort_order
    if "parent_id" in body.model_fields_set:
        new_parent_id = body.parent_id
        if new_parent_id == category.id:
            raise CategoryError("Папка не может быть родителем самой себе")
        if new_parent_id is not None:
            parent = await _owned_category(session, user.id, new_parent_id)
            if await _is_descendant(session, user.id, category.id, new_parent_id):
                raise CategoryError("Нельзя перенести папку в собственного потомка")
            if await _depth(session, parent) + await _height(session, user.id, category.id) > MAX_DEPTH:
                raise CategoryError("Слишком глубокое дерево папок")
        category.parent_id = new_parent_id
    await session.commit()
    await session.refresh(category)
    return category


async def delete_category(session: AsyncSession, user: User, category_id: int) -> None:
    category = await _owned_category(session, user.id, category_id)
    ids = await _collect_ids(session, user.id, category.id)
    await session.execute(delete(HoldingCategory).where(HoldingCategory.category_id.in_(ids)))
    for category_id in reversed(ids):
        await session.execute(delete(Category).where(Category.id == category_id, Category.user_id == user.id))
    await session.commit()


async def assign_holding(session: AsyncSession, user: User, body: AssignmentIn) -> None:
    figi = body.figi.strip()
    if not figi:
        raise CategoryError("Не указан инструмент")
    existing = (
        await session.execute(select(HoldingCategory).where(HoldingCategory.figi == figi))
    ).scalar_one_or_none()
    if body.category_id is None:
        if existing is not None:
            owner = await session.get(Category, existing.category_id)
            if owner is None or owner.user_id != user.id:
                raise CategoryError("Категория не найдена", 404)
            await session.delete(existing)
            await session.commit()
        return
    category = await _owned_category(session, user.id, body.category_id)
    if existing is None:
        session.add(HoldingCategory(category_id=category.id, figi=figi))
    else:
        owner = await session.get(Category, existing.category_id)
        if owner is None or owner.user_id != user.id:
            raise CategoryError("Категория не найдена", 404)
        existing.category_id = category.id
    await session.commit()


def _position_index(positions) -> tuple[dict[str, Decimal], dict[str, dict]]:
    values: dict[str, Decimal] = defaultdict(lambda: ZERO)
    meta: dict[str, dict] = {}
    for item in positions:
        values[item.figi] += Decimal(item.value)
        if item.figi not in meta:
            meta[item.figi] = {
                "ticker": item.ticker or item.figi,
                "name": item.name or item.figi,
                "is_cash": item.is_cash,
            }
    return values, meta


async def _user_categories(session: AsyncSession, user_id: int) -> list[Category]:
    result = await session.execute(
        select(Category).where(Category.user_id == user_id).order_by(Category.sort_order, Category.id)
    )
    return list(result.scalars())


async def _assignments(session: AsyncSession, category_ids: list[int]) -> list[HoldingCategory]:
    if not category_ids:
        return []
    result = await session.execute(
        select(HoldingCategory).where(HoldingCategory.category_id.in_(category_ids))
    )
    return list(result.scalars())


async def _owned_category(session: AsyncSession, user_id: int, category_id: int) -> Category:
    category = await session.get(Category, category_id)
    if category is None or category.user_id != user_id:
        raise CategoryError("Категория не найдена", 404)
    return category


async def _next_sort(session: AsyncSession, user_id: int, parent_id: int | None) -> int:
    query = select(func.coalesce(func.max(Category.sort_order), -1)).where(Category.user_id == user_id)
    if parent_id is None:
        query = query.where(Category.parent_id.is_(None))
    else:
        query = query.where(Category.parent_id == parent_id)
    current = await session.scalar(query)
    return int(current or -1) + 1


async def _depth(session: AsyncSession, category: Category) -> int:
    depth = 1
    current = category
    seen: set[int] = set()
    while current.parent_id:
        if current.id in seen:
            break
        seen.add(current.id)
        parent = await session.get(Category, current.parent_id)
        if parent is None:
            break
        current = parent
        depth += 1
    return depth


async def _height(session: AsyncSession, user_id: int, category_id: int) -> int:
    children = (
        await session.execute(
            select(Category).where(Category.user_id == user_id, Category.parent_id == category_id)
        )
    ).scalars()
    child_list = list(children)
    if not child_list:
        return 1
    return 1 + max([await _height(session, user_id, child.id) for child in child_list])


async def _is_descendant(session: AsyncSession, user_id: int, ancestor_id: int, node_id: int) -> bool:
    current_id: int | None = node_id
    seen: set[int] = set()
    while current_id:
        if current_id == ancestor_id:
            return True
        if current_id in seen:
            return False
        seen.add(current_id)
        node = await session.get(Category, current_id)
        if node is None or node.user_id != user_id:
            return False
        current_id = node.parent_id
    return False


async def _collect_ids(session: AsyncSession, user_id: int, root_id: int) -> list[int]:
    ids = [root_id]
    queue = [root_id]
    while queue:
        current = queue.pop()
        children = (
            await session.execute(
                select(Category.id).where(Category.user_id == user_id, Category.parent_id == current)
            )
        ).scalars()
        for child_id in children:
            ids.append(child_id)
            queue.append(child_id)
    return ids
