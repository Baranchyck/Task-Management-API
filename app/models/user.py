from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.comment import Comment
    from app.models.task import Task


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    tasks_authored: Mapped[list["Task"]] = relationship(
        "Task",
        foreign_keys="Task.author_id",
        back_populates="author",
    )
    tasks_assigned: Mapped[list["Task"]] = relationship(
        "Task",
        foreign_keys="Task.assignee_id",
        back_populates="assignee",
    )
    comments: Mapped[list["Comment"]] = relationship(
        "Comment",
        back_populates="author",
    )
