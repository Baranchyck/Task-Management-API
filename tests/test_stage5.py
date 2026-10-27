from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TaskPriority, TaskStatus
from app.models.task import Task
from app.models.user import User


async def test_comments_flow(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
):
    """Тест: додавання та читання коментарів (в т.ч. іншим користувачем)."""
    # 1. Створюємо задачу
    task_resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Task for comments"},
    )
    task_id = task_resp.json()["id"]

    # 2. Додаємо коментар від автора
    c1_resp = await client.post(
        f"/tasks/{task_id}/comments",
        headers=auth_headers,
        json={"text": "Author's initial note"},
    )
    assert c1_resp.status_code == 201
    assert c1_resp.json()["text"] == "Author's initial note"

    # 3. Додаємо коментар від іншого юзера (дозволено)
    c2_resp = await client.post(
        f"/tasks/{task_id}/comments",
        headers=other_headers,
        json={"text": "Feedback from colleague"},
    )
    assert c2_resp.status_code == 201

    # 4. Отримуємо список коментарів
    list_resp = await client.get(
        f"/tasks/{task_id}/comments",
        headers=auth_headers,
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["text"] == "Author's initial note"
    assert data["items"][1]["text"] == "Feedback from colleague"


async def test_comments_allowed_on_done_task(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_user: User,
):
    """Тест: коментарі дозволені до задач у будь-якому статусі, включно з Done."""
    # Створюємо задачу з виконавцем і дедлайном у майбутньому
    future_deadline = datetime.now(timezone.utc) + timedelta(days=1)
    task_resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Task to complete",
            "assignee_id": other_user.id,
            "deadline": future_deadline.isoformat(),
        },
    )
    task_id = task_resp.json()["id"]

    # Проходимо до Done
    await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.IN_PROGRESS.value},
    )
    await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.REVIEW.value},
    )
    await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.DONE.value},
    )

    # Додаємо коментар до завершеної задачі
    c_resp = await client.post(
        f"/tasks/{task_id}/comments",
        headers=auth_headers,
        json={"text": "Post-completion summary"},
    )
    assert c_resp.status_code == 201
    assert c_resp.json()["text"] == "Post-completion summary"


async def test_list_tasks_search_and_pagination(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Тест: пошук по q та limit/offset пагінація."""
    # Створюємо 3 задачі
    await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Fix bug in payment", "description": "urgent fix"},
    )
    await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Build landing page", "description": "marketing website"},
    )
    await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Fix auth headers", "description": "security review"},
    )

    # Пошук 'fix' (case-insensitive)
    resp = await client.get("/tasks?q=fix", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Пагінація: limit=1, offset=1
    resp_page = await client.get("/tasks?q=fix&limit=1&offset=1", headers=auth_headers)
    assert resp_page.status_code == 200
    page_data = resp_page.json()
    assert page_data["total"] == 2
    assert len(page_data["items"]) == 1
    assert page_data["limit"] == 1
    assert page_data["offset"] == 1


async def test_list_tasks_sorting_by_priority(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Тест: сортування за пріоритетом через CASE (High -> Medium -> Low)."""
    await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Low Task", "priority": TaskPriority.LOW.value},
    )
    await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "High Task", "priority": TaskPriority.HIGH.value},
    )
    await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Medium Task", "priority": TaskPriority.MEDIUM.value},
    )

    # Default sort_by=priority, order=desc
    resp = await client.get("/tasks", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["priority"] == TaskPriority.HIGH.value
    assert items[1]["priority"] == TaskPriority.MEDIUM.value
    assert items[2]["priority"] == TaskPriority.LOW.value


async def test_overdue_and_stats_endpoints(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Тест: /tasks/overdue та /tasks/stats."""
    # Створюємо звичайну задачу
    resp1 = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Normal task", "priority": TaskPriority.HIGH.value},
    )
    t1_id = resp1.json()["id"]

    # Створюємо задачу та штучно робимо її дедлайн простроченим у БД
    resp2 = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Overdue task", "priority": TaskPriority.MEDIUM.value},
    )
    t2_id = resp2.json()["id"]
    t2 = await db_session.get(Task, t2_id)
    assert t2 is not None
    t2.deadline = datetime.now(timezone.utc) - timedelta(days=2)
    await db_session.commit()

    # 1. Перевіряємо /tasks/overdue
    overdue_resp = await client.get("/tasks/overdue", headers=auth_headers)
    assert overdue_resp.status_code == 200
    overdue_data = overdue_resp.json()
    assert overdue_data["total"] == 1
    assert overdue_data["items"][0]["id"] == t2_id

    # 2. Перевіряємо /tasks/stats
    stats_resp = await client.get("/tasks/stats", headers=auth_headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total"] == 2
    assert stats["overdue_count"] == 1
    assert stats["active_count"] == 2
    # Перевіряємо наявність усіх 5 статусів та 3 пріоритетів
    assert len(stats["by_status"]) == 5
    assert len(stats["by_priority"]) == 3
    assert stats["by_priority"][TaskPriority.HIGH.value] == 1
    assert stats["by_priority"][TaskPriority.MEDIUM.value] == 1
    assert stats["by_priority"][TaskPriority.LOW.value] == 0
