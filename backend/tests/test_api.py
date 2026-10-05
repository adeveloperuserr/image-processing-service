from conftest import register, upload
from fastapi.testclient import TestClient


def test_register_and_login_issue_a_bearer_token(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "maker@example.com", "password": "PortfolioPass123"},
    )
    assert response.status_code == 201
    assert response.json()["token_type"] == "bearer"

    login = client.post(
        "/auth/login",
        json={"email": "maker@example.com", "password": "PortfolioPass123"},
    )
    assert login.status_code == 200
    assert login.json()["access_token"]


def test_transform_request_returns_a_queued_job(client: TestClient, image_bytes: bytes) -> None:
    headers = register(client, "maker@example.com")
    image_id = upload(client, headers, image_bytes)

    response = client.post(
        f"/images/{image_id}/transform",
        headers={**headers, "Idempotency-Key": "format-photo-001"},
        json={"operations": [{"type": "format", "format": "webp"}]},
    )

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "queued"
    assert job["attempt_count"] == 0
    status = client.get(job["status_url"], headers=headers).json()
    assert status["status"] == "queued"
    assert status["max_attempts"] == 4


def test_idempotency_key_replays_the_same_job(client: TestClient, image_bytes: bytes) -> None:
    headers = register(client, "maker@example.com")
    image_id = upload(client, headers, image_bytes)
    request_headers = {**headers, "Idempotency-Key": "same-transform-request"}
    payload = {"operations": [{"type": "resize", "width": 80, "height": 80}]}

    first = client.post(f"/images/{image_id}/transform", headers=request_headers, json=payload)
    second = client.post(f"/images/{image_id}/transform", headers=request_headers, json=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]


def test_idempotency_key_rejects_a_different_payload(
    client: TestClient, image_bytes: bytes
) -> None:
    headers = register(client, "maker@example.com")
    image_id = upload(client, headers, image_bytes)
    request_headers = {**headers, "Idempotency-Key": "same-request-key"}
    first = client.post(
        f"/images/{image_id}/transform",
        headers=request_headers,
        json={"operations": [{"type": "format", "format": "png"}]},
    )
    second = client.post(
        f"/images/{image_id}/transform",
        headers=request_headers,
        json={"operations": [{"type": "format", "format": "webp"}]},
    )

    assert first.status_code == 202
    assert second.status_code == 409


def test_image_and_job_are_private_to_their_owner(client: TestClient, image_bytes: bytes) -> None:
    owner_headers = register(client, "owner@example.com")
    image_id = upload(client, owner_headers, image_bytes)
    job = client.post(
        f"/images/{image_id}/transform",
        headers={**owner_headers, "Idempotency-Key": "private-job"},
        json={"operations": [{"type": "format", "format": "webp"}]},
    ).json()
    other_headers = register(client, "other@example.com")

    assert client.get(f"/images/{image_id}", headers=other_headers).status_code == 404
    assert client.get(job["status_url"], headers=other_headers).status_code == 404


def test_image_list_is_paginated_and_scoped_to_the_user(
    client: TestClient, image_bytes: bytes
) -> None:
    headers = register(client, "maker@example.com")
    upload(client, headers, image_bytes)
    upload(client, headers, image_bytes)
    register(client, "another@example.com")

    first_page = client.get("/images?page=1&limit=1", headers=headers)
    second_page = client.get("/images?page=2&limit=1", headers=headers)

    assert first_page.status_code == 200
    assert first_page.json()["total"] == 2
    assert len(first_page.json()["items"]) == 1
    assert len(second_page.json()["items"]) == 1
    assert first_page.json()["items"][0]["id"] != second_page.json()["items"][0]["id"]


def test_upload_rejects_non_image_content(client: TestClient) -> None:
    headers = register(client, "maker@example.com")
    response = client.post(
        "/images", headers=headers, files={"file": ("photo.png", b"not an image", "image/png")}
    )
    assert response.status_code == 415
