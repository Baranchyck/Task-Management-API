from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment
from app.models.task import Task
from app.schemas.comment import CommentCreate


async def create_comment(
    db: AsyncSession,
    task_id: int,
    author_id: int,
    comment_in: CommentCreate,
) -> Comment:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    comment = Comment(
        task_id=task_id,
        author_id=author_id,
        text=comment_in.text,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


async def get_comments_for_task(
    db: AsyncSession,
    task_id: int,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Comment], int]:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    count_query = select(func.count(Comment.id)).where(Comment.task_id == task_id)
    total = (await db.execute(count_query)).scalar() or 0

    query = (
        select(Comment)
        .where(Comment.task_id == task_id)
        .order_by(Comment.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await db.execute(query)).scalars().all())

    return items, total
