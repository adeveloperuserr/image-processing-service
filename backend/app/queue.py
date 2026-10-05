from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.models import ProcessingJob, utcnow


@dataclass(frozen=True)
class ClaimedJob:
    id: UUID
    image_id: UUID
    user_id: UUID
    operations_json: str
    attempt_count: int
    max_attempts: int
    lease_token: str


def _expire_exhausted_jobs(session: Session, now: datetime) -> None:
    session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.attempt_count >= ProcessingJob.max_attempts,
            (
                (ProcessingJob.status == "queued")
                | ((ProcessingJob.status == "processing") & (ProcessingJob.lease_until <= now))
            ),
        )
        .values(
            status="failed",
            lease_token=None,
            lease_until=None,
            error_code="retry_exhausted",
            error_message="El worker no completó el trabajo después de tres intentos.",
            updated_at=now,
        )
    )


def claim_next_job(
    session: Session, lease_seconds: int = 60, now: datetime | None = None
) -> ClaimedJob | None:
    current_time = now or utcnow()
    lease_token = str(uuid4())
    _expire_exhausted_jobs(session, current_time)

    if session.get_bind().dialect.name == "mssql":
        row = (
            session.execute(
                text(
                    """WITH next_job AS (
                    SELECT TOP (1) id
                    FROM processing_jobs WITH (UPDLOCK, READPAST, ROWLOCK)
                    WHERE ((status = 'queued' AND available_at <= :now)
                        OR (status = 'processing' AND lease_until <= :now))
                      AND attempt_count < max_attempts
                    ORDER BY available_at ASC, created_at ASC
                )
                UPDATE target
                SET status = 'processing',
                    attempt_count = target.attempt_count + 1,
                    lease_token = :lease_token,
                    lease_until = :lease_until,
                    error_code = NULL,
                    error_message = NULL,
                    updated_at = :now
                OUTPUT INSERTED.id, INSERTED.image_id, INSERTED.user_id,
                       INSERTED.operations_json, INSERTED.attempt_count, INSERTED.max_attempts
                FROM processing_jobs AS target
                INNER JOIN next_job ON target.id = next_job.id"""
                ),
                {
                    "now": current_time,
                    "lease_until": current_time + timedelta(seconds=lease_seconds),
                    "lease_token": lease_token,
                },
            )
            .mappings()
            .first()
        )
        session.commit()
        if row is None:
            return None
        return ClaimedJob(
            id=UUID(str(row["id"])),
            image_id=UUID(str(row["image_id"])),
            user_id=UUID(str(row["user_id"])),
            operations_json=row["operations_json"],
            attempt_count=row["attempt_count"],
            max_attempts=row["max_attempts"],
            lease_token=lease_token,
        )

    job = session.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.attempt_count < ProcessingJob.max_attempts,
            ((ProcessingJob.status == "queued") & (ProcessingJob.available_at <= current_time))
            | (
                (ProcessingJob.status == "processing") & (ProcessingJob.lease_until <= current_time)
            ),
        )
        .order_by(ProcessingJob.available_at.asc(), ProcessingJob.created_at.asc())
        .limit(1)
    )
    if job is None:
        session.commit()
        return None

    job.status = "processing"
    job.attempt_count += 1
    job.lease_token = lease_token
    job.lease_until = current_time + timedelta(seconds=lease_seconds)
    job.error_code = None
    job.error_message = None
    job.updated_at = current_time
    session.commit()
    return ClaimedJob(
        id=job.id,
        image_id=job.image_id,
        user_id=job.user_id,
        operations_json=job.operations_json,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        lease_token=lease_token,
    )


def _update_claimed_job(session: Session, claim: ClaimedJob, values: dict[str, object]) -> bool:
    result = session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == claim.id,
            ProcessingJob.status == "processing",
            ProcessingJob.lease_token == claim.lease_token,
        )
        .values(**values)
    )
    session.commit()
    return result.rowcount == 1


def mark_job_succeeded(
    session: Session,
    claim: ClaimedJob,
    output_path: str,
    content_type: str,
    size_bytes: int,
    width: int,
    height: int,
) -> bool:
    now = utcnow()
    return _update_claimed_job(
        session,
        claim,
        {
            "status": "succeeded",
            "output_path": output_path,
            "output_content_type": content_type,
            "output_size_bytes": size_bytes,
            "output_width": width,
            "output_height": height,
            "lease_token": None,
            "lease_until": None,
            "error_code": None,
            "error_message": None,
            "updated_at": now,
        },
    )


def mark_job_failed(
    session: Session,
    claim: ClaimedJob,
    error_code: str,
    message: str,
    permanent: bool = False,
) -> bool:
    now = utcnow()
    terminal = permanent or claim.attempt_count >= claim.max_attempts
    values: dict[str, object] = {
        "status": "failed" if terminal else "queued",
        "error_code": error_code,
        "error_message": message[:500],
        "lease_token": None,
        "lease_until": None,
        "updated_at": now,
    }
    if not terminal:
        delay = min(5 * (2 ** (claim.attempt_count - 1)), 60)
        values["available_at"] = now + timedelta(seconds=delay)
    return _update_claimed_job(session, claim, values)


def schedule_retry(session: Session, claim: ClaimedJob, error_code: str, message: str) -> bool:
    return mark_job_failed(session, claim, error_code, message, permanent=False)
