from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentRead
from app.schemas.common import PaginatedResponse
from app.services import comment_service

router = APIRouter(prefix="/tasks", tags=["Comments"])


@router.post(
    "/{id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Додавання коментаря до задачі",
)
async def create_comment(
    id: int,
    comment_in: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await comment_service.create_comment(
        db=db,
        task_id=id,
        author_id=current_user.id,
        comment_in=comment_in,
    )


@router.get(
    "/{id}/comments",
    response_model=PaginatedResponse[CommentRead],
    summary="Отримання списку коментарів до задачі з пагінацією",
)
async def get_comments(
    id: int,
    limit: int = Query(20, ge=1, le=100, description="Кількість коментарів на сторінку"),
    offset: int = Query(0, ge=0, description="Зсув для пагінації"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await comment_service.get_comments_for_task(
        db=db,
        task_id=id,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
