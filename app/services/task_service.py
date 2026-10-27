from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TaskPriority, TaskStatus
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskStats, TaskUpdate
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


async def list_tasks(
    db: AsyncSession,
    q: str | None = None,
    status_filter: TaskStatus | None = None,
    priority_filter: TaskPriority | None = None,
    assignee_id: int | None = None,
    deadline_from: datetime | None = None,
    deadline_to: datetime | None = None,
    sort_by: str = "priority",
    order: str = "desc",
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Task], int]:
    query = select(Task)
    count_query = select(func.count(Task.id))

    filters = []

    if q:
        search_pattern = f"%{q}%"
        filters.append(
            or_(
                Task.title.ilike(search_pattern),
                Task.description.ilike(search_pattern),
            )
        )

    if status_filter is not None:
        filters.append(Task.status == status_filter)

    if priority_filter is not None:
        filters.append(Task.priority == priority_filter)

    if assignee_id is not None:
        filters.append(Task.assignee_id == assignee_id)

    if deadline_from is not None:
        filters.append(Task.deadline >= deadline_from)

    if deadline_to is not None:
        filters.append(Task.deadline <= deadline_to)

    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    total = (await db.execute(count_query)).scalar() or 0

    # Sorting
    is_desc = order.lower() == "desc"

    if sort_by == "priority":
        priority_case = case(
            (Task.priority == TaskPriority.HIGH, 3),
            (Task.priority == TaskPriority.MEDIUM, 2),
            (Task.priority == TaskPriority.LOW, 1),
            else_=0,
        )
        if is_desc:
            query = query.order_by(
                priority_case.desc(),
                Task.deadline.asc().nulls_last(),
            )
        else:
            query = query.order_by(
                priority_case.asc(),
                Task.deadline.asc().nulls_last(),
            )
    elif sort_by == "deadline":
        if is_desc:
            query = query.order_by(Task.deadline.desc().nulls_last())
        else:
            query = query.order_by(Task.deadline.asc().nulls_last())
    elif sort_by == "created_at":
        if is_desc:
            query = query.order_by(Task.created_at.desc())
        else:
            query = query.order_by(Task.created_at.asc())
    else:
        # Fallback to default sorting: priority DESC, deadline ASC NULLS LAST
        priority_case = case(
            (Task.priority == TaskPriority.HIGH, 3),
            (Task.priority == TaskPriority.MEDIUM, 2),
            (Task.priority == TaskPriority.LOW, 1),
            else_=0,
        )
        query = query.order_by(
            priority_case.desc(),
            Task.deadline.asc().nulls_last(),
        )

    query = query.limit(limit).offset(offset)
    tasks = list((await db.execute(query)).scalars().all())

    return tasks, total


async def get_overdue_tasks(
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Task], int]:
    now = datetime.now(timezone.utc)
    conditions = [
        Task.deadline < now,
        Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
    ]

    count_query = select(func.count(Task.id)).where(*conditions)
    total = (await db.execute(count_query)).scalar() or 0

    query = (
        select(Task)
        .where(*conditions)
        .order_by(Task.deadline.asc())
        .limit(limit)
        .offset(offset)
    )
    tasks = list((await db.execute(query)).scalars().all())

    return tasks, total


async def get_task_stats(db: AsyncSession) -> TaskStats:
    now = datetime.now(timezone.utc)

    total = (await db.execute(select(func.count(Task.id)))).scalar() or 0

    # Status distribution
    status_query = select(Task.status, func.count(Task.id)).group_by(Task.status)
    status_rows = (await db.execute(status_query)).all()
    by_status = {s.value: 0 for s in TaskStatus}
    for status_val, count in status_rows:
        key = status_val.value if hasattr(status_val, "value") else str(status_val)
        by_status[key] = count

    # Priority distribution
    priority_query = select(Task.priority, func.count(Task.id)).group_by(Task.priority)
    priority_rows = (await db.execute(priority_query)).all()
    by_priority = {p.value: 0 for p in TaskPriority}
    for prio_val, count in priority_rows:
        key = prio_val.value if hasattr(prio_val, "value") else str(prio_val)
        by_priority[key] = count

    # Overdue count
    overdue_query = select(func.count(Task.id)).where(
        Task.deadline < now,
        Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
    )
    overdue_count = (await db.execute(overdue_query)).scalar() or 0

    # Active count
    active_query = select(func.count(Task.id)).where(
        Task.status.in_(ACTIVE_STATUSES),
    )
    active_count = (await db.execute(active_query)).scalar() or 0

    return TaskStats(
        total=total,
        by_status=by_status,
        by_priority=by_priority,
        overdue_count=overdue_count,
        active_count=active_count,
    )

