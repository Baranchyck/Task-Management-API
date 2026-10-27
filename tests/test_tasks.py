from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TaskPriority, TaskStatus
from app.models.task import Task
from app.models.user import User


async def test_disallowed_status_transition_review_to_in_progress(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_user: User,
):
    """Тест: заборонений перехід зі статусу Review назад в In Progress."""
    create_resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Test Transition Task",
            "assignee_id": other_user.id,
        },
    )
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.IN_PROGRESS.value},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == TaskStatus.IN_PROGRESS.value

    resp = await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.REVIEW.value},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == TaskStatus.REVIEW.value

    resp = await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.IN_PROGRESS.value},
    )
    assert resp.status_code == 409
    assert "not allowed" in resp.json()["detail"]


async def test_active_tasks_limit_eleventh_task(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_user: User,
):
    """Тест: виконавець не може мати більше 10 активних задач (11-та повертає 409)."""
    for i in range(10):
        resp = await client.post(
            "/tasks",
            headers=auth_headers,
            json={
                "title": f"Active Task {i + 1}",
                "assignee_id": other_user.id,
            },
        )
        assert resp.status_code == 201

    resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "11th Task",
            "assignee_id": other_user.id,
        },
    )
    assert resp.status_code == 409
    assert "10 active tasks" in resp.json()["detail"]


async def test_assign_eleventh_task_via_update(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_user: User,
):
    """Тест: призначення 11-ї активної задачі через PATCH /tasks/{id} повертає 409."""
    unassigned_resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Unassigned Task"},
    )
    assert unassigned_resp.status_code == 201
    unassigned_id = unassigned_resp.json()["id"]

    for i in range(10):
        resp = await client.post(
            "/tasks",
            headers=auth_headers,
            json={"title": f"Task {i + 1}", "assignee_id": other_user.id},
        )
        assert resp.status_code == 201

    patch_resp = await client.patch(
        f"/tasks/{unassigned_id}",
        headers=auth_headers,
        json={"assignee_id": other_user.id},
    )
    assert patch_resp.status_code == 409
    assert "10 active tasks" in patch_resp.json()["detail"]


async def test_cannot_transition_to_done_without_assignee(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Тест: перехід у Done заборонений, якщо у задачі немає виконавця."""
    resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Task without assignee"},
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

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

    resp = await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.DONE.value},
    )
    assert resp.status_code == 409
    assert "without an assignee" in resp.json()["detail"]


async def test_cannot_delete_task_in_in_progress_or_review(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Тест: видалення задачі заборонене у статусах In Progress та Review."""
    resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Task to delete"},
    )
    task_id = resp.json()["id"]

    await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.IN_PROGRESS.value},
    )

    del_resp = await client.delete(f"/tasks/{task_id}", headers=auth_headers)
    assert del_resp.status_code == 409
    assert "In Progress" in del_resp.json()["detail"]

    await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.REVIEW.value},
    )

    del_resp = await client.delete(f"/tasks/{task_id}", headers=auth_headers)
    assert del_resp.status_code == 409
    assert "Review" in del_resp.json()["detail"]


async def test_deadline_in_past_validation_on_create(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Тест: дедлайн у минулому при створенні повертає 422."""
    past_deadline = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Past Deadline Task",
            "deadline": past_deadline,
        },
    )
    assert resp.status_code == 422


async def test_cannot_transition_to_done_with_overdue_deadline(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_user: User,
    db_session: AsyncSession,
):
    """Тест: перехід у Done заборонений, якщо дедлайн минув."""
    future_deadline = datetime.now(timezone.utc) + timedelta(days=2)
    resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Overdue candidate task",
            "assignee_id": other_user.id,
            "deadline": future_deadline.isoformat(),
        },
    )
    task_id = resp.json()["id"]

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

    task = await db_session.get(Task, task_id)
    assert task is not None
    task.deadline = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()

    done_resp = await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.DONE.value},
    )
    assert done_resp.status_code == 409
    assert "deadline has passed" in done_resp.json()["detail"]


async def test_cannot_change_assignee_in_review(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_user: User,
    test_user: User,
):
    """Тест: заборона зміни виконавця у статусі Review."""
    resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Task in Review",
            "assignee_id": other_user.id,
        },
    )
    task_id = resp.json()["id"]

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

    resp = await client.patch(
        f"/tasks/{task_id}",
        headers=auth_headers,
        json={"assignee_id": test_user.id},
    )
    assert resp.status_code == 409
    assert "Cannot change assignee in Review" in resp.json()["detail"]


async def test_non_author_cannot_edit_or_delete_task(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
):
    """Тест: користувач, який не є автором, не може редагувати або видаляти задачу (403)."""
    resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Author's Task"},
    )
    task_id = resp.json()["id"]

    edit_resp = await client.patch(
        f"/tasks/{task_id}",
        headers=other_headers,
        json={"title": "Hacked Title"},
    )
    assert edit_resp.status_code == 403

    del_resp = await client.delete(
        f"/tasks/{task_id}",
        headers=other_headers,
    )
    assert del_resp.status_code == 403
