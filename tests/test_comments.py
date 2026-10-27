from datetime import datetime, timedelta, timezone
from httpx import AsyncClient

from app.models.enums import TaskStatus
from app.models.user import User


async def test_create_and_read_comments(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
):
    task_resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Task for comments test"},
    )
    task_id = task_resp.json()["id"]

    # Author leaves comment
    c1 = await client.post(
        f"/tasks/{task_id}/comments",
        headers=auth_headers,
        json={"text": "Author comment"},
    )
    assert c1.status_code == 201
    assert c1.json()["text"] == "Author comment"

    # Other user leaves comment
    c2 = await client.post(
        f"/tasks/{task_id}/comments",
        headers=other_headers,
        json={"text": "Colleague review note"},
    )
    assert c2.status_code == 201

    # Fetch comments list
    res = await client.get(f"/tasks/{task_id}/comments", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["text"] == "Author comment"
    assert data["items"][1]["text"] == "Colleague review note"


async def test_comments_allowed_on_done_task(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_user: User,
):
    # Create task with assignee and complete it
    deadline = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    t_resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Task to complete",
            "assignee_id": other_user.id,
            "deadline": deadline,
        },
    )
    task_id = t_resp.json()["id"]

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

    # Commenting on Done task should be allowed
    resp = await client.post(
        f"/tasks/{task_id}/comments",
        headers=auth_headers,
        json={"text": "Post-completion summary comment"},
    )
    assert resp.status_code == 201
    assert resp.json()["text"] == "Post-completion summary comment"


async def test_comment_on_nonexistent_task(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    resp = await client.post(
        "/tasks/999999/comments",
        headers=auth_headers,
        json={"text": "This should fail"},
    )
    assert resp.status_code == 404
