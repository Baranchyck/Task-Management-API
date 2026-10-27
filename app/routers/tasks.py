from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.task import TaskCreate, TaskRead, TaskStatusUpdate, TaskUpdate
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
