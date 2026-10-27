from enum import Enum


class TaskStatus(str, Enum):
    BACKLOG = "Backlog"
    IN_PROGRESS = "In Progress"
    REVIEW = "Review"
    DONE = "Done"
    CANCELLED = "Cancelled"


class TaskPriority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
