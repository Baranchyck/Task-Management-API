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
    """Тест: функція автоскасування напряму скасовує прострочені задачі."""
    now = datetime.now(timezone.utc)
    past_date = now - timedelta(hours=2)
    future_date = now + timedelta(days=2)

    # 1. Прострочена задача у Backlog -> має стати Cancelled
    t1 = Task(
        title="Overdue Backlog Task",
        status=TaskStatus.BACKLOG,
        priority=TaskPriority.MEDIUM,
        author_id=test_user.id,
        deadline=past_date,
    )
    # 2. Прострочена задача у Review -> має стати Cancelled (обходить звичайні переходи)
    t2 = Task(
        title="Overdue Review Task",
        status=TaskStatus.REVIEW,
        priority=TaskPriority.HIGH,
        author_id=test_user.id,
        deadline=past_date,
    )
    # 3. Задача з дедлайном у майбутньому -> залишається In Progress
    t3 = Task(
        title="Future Task",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.LOW,
        author_id=test_user.id,
        deadline=future_date,
    )
    # 4. Задача у Done з минулим дедлайном -> залишається Done
    t4 = Task(
        title="Completed Task",
        status=TaskStatus.DONE,
        priority=TaskPriority.MEDIUM,
        author_id=test_user.id,
        deadline=past_date,
    )
    # 5. Задача без дедлайну -> залишається Backlog
    t5 = Task(
        title="No deadline Task",
        status=TaskStatus.BACKLOG,
        priority=TaskPriority.MEDIUM,
        author_id=test_user.id,
        deadline=None,
    )

    db_session.add_all([t1, t2, t3, t4, t5])
    await db_session.commit()

    # Викликаємо функцію автоскасування напряму
    cancelled_count = await cancel_overdue_tasks(session=db_session)

    assert cancelled_count == 2

    # Перевіряємо статуси в базі
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
