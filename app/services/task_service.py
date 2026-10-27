from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TaskStatus
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.transitions import ACTIVE_STATUSES, can_transition


async def count_active_tasks(db: AsyncSession, assignee_id: int) -> int:
    query = select(func.count(Task.id)).where(
        Task.assignee_id == assignee_id,
        Task.status.in_(ACTIVE_STATUSES),
    )
    result = await db.execute(query)
    return result.scalar() or 0


async def get_task_by_id(db: AsyncSession, task_id: int) -> Task:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return task


async def create_task(db: AsyncSession, task_in: TaskCreate, author_id: int) -> Task:
    if task_in.assignee_id is not None:
        assignee = await db.get(User, task_in.assignee_id)
        if not assignee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignee not found",
            )
        active_count = await count_active_tasks(db, task_in.assignee_id)
        if active_count >= 10:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Assignee cannot have more than 10 active tasks",
            )

    new_task = Task(
        title=task_in.title,
        description=task_in.description,
        priority=task_in.priority,
        status=TaskStatus.BACKLOG,
        author_id=author_id,
        assignee_id=task_in.assignee_id,
        deadline=task_in.deadline,
    )
    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    return new_task


async def update_task(
    db: AsyncSession,
    task_id: int,
    task_in: TaskUpdate,
    current_user_id: int,
) -> Task:
    task = await get_task_by_id(db, task_id)

    if task.author_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can edit this task",
        )

    if task.status in (TaskStatus.DONE, TaskStatus.CANCELLED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot edit task in {task.status.value} status",
        )

    fields_set = task_in.model_fields_set

    if "assignee_id" in fields_set:
        new_assignee_id = task_in.assignee_id
        if new_assignee_id != task.assignee_id:
            if task.status in (TaskStatus.REVIEW, TaskStatus.DONE):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot change assignee in Review or Done status",
                )
            if new_assignee_id is not None:
                assignee = await db.get(User, new_assignee_id)
                if not assignee:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Assignee not found",
                    )
                active_count = await count_active_tasks(db, new_assignee_id)
                if active_count >= 10:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Assignee cannot have more than 10 active tasks",
                    )
            task.assignee_id = new_assignee_id

    if "deadline" in fields_set:
        new_deadline = task_in.deadline
        if new_deadline != task.deadline:
            if new_deadline is not None and new_deadline < datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Deadline cannot be in the past",
                )
            task.deadline = new_deadline

    if "title" in fields_set and task_in.title is not None:
        task.title = task_in.title

    if "description" in fields_set:
        task.description = task_in.description

    if "priority" in fields_set and task_in.priority is not None:
        task.priority = task_in.priority

    task.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)
    return task


async def update_task_status(
    db: AsyncSession,
    task_id: int,
    new_status: TaskStatus,
    current_user_id: int,
) -> Task:
    task = await get_task_by_id(db, task_id)

    if current_user_id != task.author_id and current_user_id != task.assignee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author or assignee can change the task status",
        )

    if task.status == new_status:
        return task

    if not can_transition(task.status, new_status):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Transition from '{task.status.value}' to '{new_status.value}' is not allowed",
        )

    if new_status == TaskStatus.DONE:
        if task.assignee_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot transition to Done without an assignee",
            )
        if task.deadline is not None and task.deadline < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot transition to Done when deadline has passed",
            )

    task.status = new_status
    task.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)
    return task


async def delete_task(
    db: AsyncSession,
    task_id: int,
    current_user_id: int,
) -> None:
    task = await get_task_by_id(db, task_id)

    if task.author_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can delete this task",
        )

    if task.status in (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete task in '{task.status.value}' status",
        )

    await db.delete(task)
    await db.commit()
