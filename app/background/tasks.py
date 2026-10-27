import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_maker
from app.models.enums import TaskStatus
from app.models.task import Task

logger = logging.getLogger(__name__)


async def cancel_overdue_tasks(session: AsyncSession | None = None) -> int:
    """Виконує один bulk UPDATE для автоскасування прострочених задач."""
    now = datetime.now(timezone.utc)
    stmt = (
        update(Task)
        .where(
            Task.deadline < now,
            Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
        )
        .values(
            status=TaskStatus.CANCELLED,
            updated_at=now,
        )
    )

    if session is not None:
        result = await session.execute(stmt)
        await session.commit()
        cancelled_count = result.rowcount or 0
    else:
        async with async_session_maker() as sess:
            result = await sess.execute(stmt)
            await sess.commit()
            cancelled_count = result.rowcount or 0

    if cancelled_count > 0:
        logger.info("Auto-cancelled %d overdue tasks", cancelled_count)
    return cancelled_count


async def run_overdue_tasks_worker() -> None:
    """Періодичний воркер, що запускається у lifespan додатку."""
    logger.info(
        "Overdue tasks worker started. Interval: %s seconds",
        settings.OVERDUE_CHECK_INTERVAL_SECONDS,
    )
    while True:
        try:
            await cancel_overdue_tasks()
        except asyncio.CancelledError:
            logger.info("Overdue tasks worker received cancellation signal.")
            raise
        except Exception:
            logger.exception("Error occurred in overdue tasks worker loop.")

        await asyncio.sleep(settings.OVERDUE_CHECK_INTERVAL_SECONDS)
