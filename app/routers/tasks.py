from datetime import datetime
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.enums import TaskPriority, TaskStatus
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.task import (
    TaskCreate,
    TaskRead,
    TaskStats,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Створення нової задачі",
)
async def create_task(
    task_in: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await task_service.create_task(
        db=db,
        task_in=task_in,
        author_id=current_user.id,
    )


@router.get(
    "",
    response_model=PaginatedResponse[TaskRead],
    summary="Отримання списку задач з пошуком, фільтрами, сортуванням та пагінацією",
)
async def list_tasks(
    q: str | None = Query(None, description="Пошук по title та description"),
    status: TaskStatus | None = Query(None, description="Фільтр за статусом"),
    priority: TaskPriority | None = Query(None, description="Фільтр за пріоритетом"),
    assignee_id: int | None = Query(None, description="Фільтр за виконавцем"),
    deadline_from: datetime | None = Query(None, description="Дедлайн від (UTC)"),
    deadline_to: datetime | None = Query(None, description="Дедлайн до (UTC)"),
    sort_by: str = Query("priority", description="Поле сортування: priority, created_at, deadline"),
    order: str = Query("desc", description="Напрямок сортування: asc, desc"),
    limit: int = Query(20, ge=1, le=100, description="Кількість задач на сторінку"),
    offset: int = Query(0, ge=0, description="Зсув для пагінації"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await task_service.list_tasks(
        db=db,
        q=q,
        status_filter=status,
        priority_filter=priority,
        assignee_id=assignee_id,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
        sort_by=sort_by,
        order=order,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/overdue",
    response_model=PaginatedResponse[TaskRead],
    summary="Отримання списку прострочених задач",
)
async def get_overdue_tasks(
    limit: int = Query(20, ge=1, le=100, description="Кількість задач на сторінку"),
    offset: int = Query(0, ge=0, description="Зсув для пагінації"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await task_service.get_overdue_tasks(
        db=db,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/stats",
    response_model=TaskStats,
    summary="Отримання агрегованої статистики по задачах",
)
async def get_task_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await task_service.get_task_stats(db=db)


@router.get(
    "/{id}",
    response_model=TaskRead,
    summary="Отримання задачі за ID",
)
async def get_task(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await task_service.get_task_by_id(db=db, task_id=id)


@router.patch(
    "/{id}",
    response_model=TaskRead,
    summary="Редагування задачі (без статусу)",
)
async def update_task(
    id: int,
    task_in: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await task_service.update_task(
        db=db,
        task_id=id,
        task_in=task_in,
        current_user_id=current_user.id,
    )


@router.patch(
    "/{id}/status",
    response_model=TaskRead,
    summary="Зміна статусу задачі",
)
async def update_task_status(
    id: int,
    status_in: TaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await task_service.update_task_status(
        db=db,
        task_id=id,
        new_status=status_in.status,
        current_user_id=current_user.id,
    )


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Видалення задачі",
)
async def delete_task(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await task_service.delete_task(
        db=db,
        task_id=id,
        current_user_id=current_user.id,
    )
