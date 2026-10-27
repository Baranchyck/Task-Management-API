from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.models.enums import TaskPriority, TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: int | None = None
    deadline: datetime | None = None

    @field_validator("deadline")
    @classmethod
    def validate_deadline_future(cls, v: datetime | None) -> datetime | None:
        if v is not None:
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            if v < datetime.now(timezone.utc):
                raise ValueError("Deadline must be in the future")
        return v


class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    priority: TaskPriority | None = None
    assignee_id: int | None = None
    deadline: datetime | None = None

    @field_validator("deadline")
    @classmethod
    def normalize_deadline(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskRead(BaseModel):
    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    author_id: int
    assignee_id: int | None
    deadline: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskStats(BaseModel):
    total: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    overdue_count: int
    active_count: int

