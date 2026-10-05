from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import create_app
from app.settings import Settings


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        jwt_secret="test-secret-with-enough-entropy-for-local-test-only",
        data_dir=tmp_path,
        max_upload_bytes=1024 * 1024,
    )
    app = create_app(settings=settings, session_factory=session_factory)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(engine)
    engine.dispose()


def sample_image_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (160, 90), "#315a53")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def image_bytes() -> bytes:
    return sample_image_bytes()


def register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/auth/register", json={"email": email, "password": "PortfolioPass123"})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def upload(client: TestClient, headers: dict[str, str], image_bytes: bytes) -> str:
    response = client.post(
        "/images",
        headers=headers,
        files={"file": ("photo.png", image_bytes, "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]
