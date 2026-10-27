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
    create_resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Test Transition Task", "assignee_id": other_user.id},
    )
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    # Backlog -> In Progress -> Review
    r1 = await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.IN_PROGRESS.value},
    )
    assert r1.status_code == 200

    r2 = await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.REVIEW.value},
    )
    assert r2.status_code == 200

    # Review -> In Progress is forbidden
    r3 = await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.IN_PROGRESS.value},
    )
    assert r3.status_code == 409
    assert "not allowed" in r3.json()["detail"].lower()


async def test_active_tasks_limit_eleventh_task(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_user: User,
):
    # Create 10 active tasks for assignee
    for i in range(10):
        resp = await client.post(
            "/tasks",
            headers=auth_headers,
            json={"title": f"Active Task {i + 1}", "assignee_id": other_user.id},
        )
        assert resp.status_code == 201

    # 11th active task must fail
    resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "11th Task", "assignee_id": other_user.id},
    )
    assert resp.status_code == 409
    assert "10 active tasks" in resp.json()["detail"].lower()


async def test_assign_eleventh_task_via_update(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_user: User,
):
    unassigned = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Unassigned Task"},
    )
    assert unassigned.status_code == 201
    unassigned_id = unassigned.json()["id"]

    # Fill up 10 active tasks for assignee
    for i in range(10):
        resp = await client.post(
            "/tasks",
            headers=auth_headers,
            json={"title": f"Task {i + 1}", "assignee_id": other_user.id},
        )
        assert resp.status_code == 201

    # Assigning via PATCH must also enforce the limit
    patch_resp = await client.patch(
        f"/tasks/{unassigned_id}",
        headers=auth_headers,
        json={"assignee_id": other_user.id},
    )
    assert patch_resp.status_code == 409
    assert "10 active tasks" in patch_resp.json()["detail"].lower()


async def test_cannot_transition_to_done_without_assignee(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Task without assignee"},
    )
    task_id = resp.json()["id"]

    # Advance to Review
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

    # Transitioning to Done without assignee is rejected
    done_resp = await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.DONE.value},
    )
    assert done_resp.status_code == 409
    assert "without an assignee" in done_resp.json()["detail"].lower()


async def test_cannot_delete_task_in_in_progress_or_review(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Task to delete"},
    )
    task_id = resp.json()["id"]

    # In Progress deletion
    await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.IN_PROGRESS.value},
    )
    d1 = await client.delete(f"/tasks/{task_id}", headers=auth_headers)
    assert d1.status_code == 409

    # Review deletion
    await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": TaskStatus.REVIEW.value},
    )
    d2 = await client.delete(f"/tasks/{task_id}", headers=auth_headers)
    assert d2.status_code == 409


async def test_deadline_in_past_validation_on_create(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    past_deadline = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Past Deadline Task", "deadline": past_deadline},
    )
    assert resp.status_code == 422


async def test_cannot_transition_to_done_with_overdue_deadline(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_user: User,
    db_session: AsyncSession,
):
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

    # Simulate expired deadline in DB
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
    assert "passed" in done_resp.json()["detail"].lower()


async def test_cannot_change_assignee_in_review(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_user: User,
    test_user: User,
):
    resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Task in Review", "assignee_id": other_user.id},
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

    patch_resp = await client.patch(
        f"/tasks/{task_id}",
        headers=auth_headers,
        json={"assignee_id": test_user.id},
    )
    assert patch_resp.status_code == 409
    assert "review" in patch_resp.json()["detail"].lower()


async def test_non_author_cannot_edit_or_delete_task(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
):
    resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Author's Task"},
    )
    task_id = resp.json()["id"]

    # Forbidden for non-author
    edit_resp = await client.patch(
        f"/tasks/{task_id}",
        headers=other_headers,
        json={"title": "Hacked Title"},
    )
    assert edit_resp.status_code == 403

    del_resp = await client.delete(f"/tasks/{task_id}", headers=other_headers)
    assert del_resp.status_code == 403


async def test_list_tasks_search_and_pagination(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
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

    # Search by q
    resp = await client.get("/tasks?q=fix", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Limit and offset
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

    # Default sorting: High -> Medium -> Low
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
    await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Normal task", "priority": TaskPriority.HIGH.value},
    )

    resp2 = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Overdue task", "priority": TaskPriority.MEDIUM.value},
    )
    t2_id = resp2.json()["id"]

    # Set deadline in the past
    t2 = await db_session.get(Task, t2_id)
    assert t2 is not None
    t2.deadline = datetime.now(timezone.utc) - timedelta(days=2)
    await db_session.commit()

    # /tasks/overdue
    overdue_resp = await client.get("/tasks/overdue", headers=auth_headers)
    assert overdue_resp.status_code == 200
    overdue_data = overdue_resp.json()
    assert overdue_data["total"] == 1
    assert overdue_data["items"][0]["id"] == t2_id

    # /tasks/stats
    stats_resp = await client.get("/tasks/stats", headers=auth_headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total"] == 2
    assert stats["overdue_count"] == 1
    assert stats["active_count"] == 2
    assert len(stats["by_status"]) == 5
    assert len(stats["by_priority"]) == 3
