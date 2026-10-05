import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from conftest import sample_image_bytes
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import ImageAsset, ProcessingJob, User, utcnow
from app.queue import claim_next_job, mark_job_failed, schedule_retry
from app.storage import ImageStorage
from app.worker import run_claimed_job


def prepared_job(tmp_path: Path, operations: list[dict[str, object]] | None = None):
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    storage = ImageStorage(tmp_path / "assets")
    user = User(email="worker@example.com", password_hash="test")
    image = ImageAsset(
        id=uuid4(),
        user_id=user.id,
        original_name="sample.png",
        original_path="pending",
        content_type="image/png",
        size_bytes=len(sample_image_bytes()),
        width=160,
        height=90,
    )
    session = session_factory()
    session.add(user)
    session.flush()
    image.user_id = user.id
    image.original_path = storage.save_original(
        user.id, image.id, "image/png", sample_image_bytes()
    )
    session.add(image)
    job = ProcessingJob(
        user_id=user.id,
        image_id=image.id,
        operations_json=json.dumps(operations or [{"type": "format", "format": "webp"}]),
        request_fingerprint="f" * 64,
        idempotency_key=str(uuid4()),
        status="queued",
        max_attempts=4,
        available_at=utcnow(),
    )
    session.add(job)
    session.commit()
    job_id = job.id
    user_id = user.id
    session.close()
    return engine, session_factory, storage, user_id, image.id, job_id


def test_claim_marks_job_processing_and_counts_the_attempt(tmp_path: Path) -> None:
    engine, session_factory, _, _, _, job_id = prepared_job(tmp_path)
    now = utcnow()
    with session_factory() as session:
        claim = claim_next_job(session, lease_seconds=60, now=now)
        job = session.get(ProcessingJob, job_id)

    assert claim is not None
    assert claim.id == job_id
    assert job.status == "processing"
    assert job.attempt_count == 1
    assert job.lease_until == now + timedelta(seconds=60)
    engine.dispose()


def test_expired_lease_requeues_with_a_new_token(tmp_path: Path) -> None:
    engine, session_factory, _, _, _, job_id = prepared_job(tmp_path)
    start = utcnow()
    with session_factory() as session:
        first = claim_next_job(session, lease_seconds=1, now=start)
        second = claim_next_job(session, lease_seconds=1, now=start + timedelta(seconds=2))
        job = session.get(ProcessingJob, job_id)

    assert first is not None and second is not None
    assert first.lease_token != second.lease_token
    assert second.attempt_count == 2
    assert job.status == "processing"
    engine.dispose()


def test_expired_lease_after_last_attempt_marks_job_failed(tmp_path: Path) -> None:
    engine, session_factory, _, _, _, job_id = prepared_job(tmp_path)
    start = utcnow()
    with session_factory() as session:
        first = claim_next_job(session, lease_seconds=1, now=start)
        second = claim_next_job(session, lease_seconds=1, now=start + timedelta(seconds=2))
        third = claim_next_job(session, lease_seconds=1, now=start + timedelta(seconds=4))
        fourth = claim_next_job(session, lease_seconds=1, now=start + timedelta(seconds=6))
        no_fifth_attempt = claim_next_job(
            session, lease_seconds=1, now=start + timedelta(seconds=8)
        )
        job = session.get(ProcessingJob, job_id)

    assert first is not None and second is not None and third is not None and fourth is not None
    assert no_fifth_attempt is None
    assert job.attempt_count == 4
    assert job.status == "failed"
    assert job.error_code == "retry_exhausted"
    engine.dispose()


def test_success_writes_one_result_and_job_is_no_longer_claimable(tmp_path: Path) -> None:
    engine, session_factory, storage, _, _, job_id = prepared_job(tmp_path)
    with session_factory() as session:
        claim = claim_next_job(session, lease_seconds=60)
    assert claim is not None

    assert run_claimed_job(claim, session_factory, storage, heartbeat_seconds=0)
    with session_factory() as session:
        job = session.get(ProcessingJob, job_id)
        second_claim = claim_next_job(session, lease_seconds=60)

    assert job.status == "succeeded"
    assert job.output_content_type == "image/webp"
    assert storage.resolve(job.output_path).is_file()
    assert second_claim is None
    engine.dispose()


def test_permanent_transform_error_does_not_retry(tmp_path: Path) -> None:
    invalid_crop = [{"type": "crop", "x": 159, "y": 0, "width": 10, "height": 20}]
    engine, session_factory, storage, _, _, job_id = prepared_job(tmp_path, invalid_crop)
    with session_factory() as session:
        claim = claim_next_job(session, lease_seconds=60)
    assert claim is not None

    run_claimed_job(claim, session_factory, storage, heartbeat_seconds=0)
    with session_factory() as session:
        job = session.get(ProcessingJob, job_id)

    assert job.status == "failed"
    assert job.attempt_count == 1
    assert job.error_code == "transform_invalid"
    engine.dispose()


def test_stale_worker_cannot_change_job_after_lease_was_reclaimed(tmp_path: Path) -> None:
    engine, session_factory, _, _, _, job_id = prepared_job(tmp_path)
    start = utcnow()
    with session_factory() as session:
        stale = claim_next_job(session, lease_seconds=1, now=start)
        current = claim_next_job(session, lease_seconds=1, now=start + timedelta(seconds=2))
        mark_job_failed(session, stale, "stale", "stale worker", permanent=True)
        job = session.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id))

    assert stale is not None and current is not None
    assert job.lease_token == current.lease_token
    assert job.status == "processing"
    engine.dispose()


def test_transient_failure_is_scheduled_for_retry(tmp_path: Path) -> None:
    engine, session_factory, _, _, _, job_id = prepared_job(tmp_path)
    with session_factory() as session:
        claim = claim_next_job(session, lease_seconds=60)
        assert claim is not None
        schedule_retry(session, claim, "storage_unavailable", "El almacenamiento está ocupado.")
        job = session.get(ProcessingJob, job_id)

    assert job.status == "queued"
    assert job.attempt_count == 1
    assert job.available_at > utcnow()
    assert job.error_code == "storage_unavailable"
    engine.dispose()
