from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.background.tasks import cancel_overdue_tasks
from app.models.enums import TaskPriority, TaskStatus
from app.models.task import Task
from app.models.user import User


async def test_cancel_overdue_tasks_bulk(
    db_session: AsyncSession,
    test_user: User,
):
    now = datetime.now(timezone.utc)
    past_date = now - timedelta(hours=2)
    future_date = now + timedelta(days=2)

    # Overdue tasks in Backlog & Review
    t1 = Task(
        title="Overdue Backlog Task",
        status=TaskStatus.BACKLOG,
        priority=TaskPriority.MEDIUM,
        author_id=test_user.id,
        deadline=past_date,
    )
    t2 = Task(
        title="Overdue Review Task",
        status=TaskStatus.REVIEW,
        priority=TaskPriority.HIGH,
        author_id=test_user.id,
        deadline=past_date,
    )
    # Tasks that should NOT be cancelled
    t3 = Task(
        title="Future Task",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.LOW,
        author_id=test_user.id,
        deadline=future_date,
    )
    t4 = Task(
        title="Completed Task",
        status=TaskStatus.DONE,
        priority=TaskPriority.MEDIUM,
        author_id=test_user.id,
        deadline=past_date,
    )
    t5 = Task(
        title="No deadline Task",
        status=TaskStatus.BACKLOG,
        priority=TaskPriority.MEDIUM,
        author_id=test_user.id,
        deadline=None,
    )

    db_session.add_all([t1, t2, t3, t4, t5])
    await db_session.commit()

    cancelled_count = await cancel_overdue_tasks(session=db_session)
    assert cancelled_count == 2

    await db_session.refresh(t1)
    await db_session.refresh(t2)
    await db_session.refresh(t3)
    await db_session.refresh(t4)
    await db_session.refresh(t5)

    assert t1.status == TaskStatus.CANCELLED
    assert t2.status == TaskStatus.CANCELLED
    assert t3.status == TaskStatus.IN_PROGRESS
    assert t4.status == TaskStatus.DONE
    assert t5.status == TaskStatus.BACKLOG
