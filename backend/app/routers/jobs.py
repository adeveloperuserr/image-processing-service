from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import ProcessingJob, User
from app.schemas import JobResponse
from app.storage import ImageStorage

router = APIRouter(prefix="/jobs", tags=["trabajos"])
DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _get_owned_job(db: Session, user_id: UUID, job_id: UUID) -> ProcessingJob:
    job = db.scalar(
        select(ProcessingJob).where(ProcessingJob.id == job_id, ProcessingJob.user_id == user_id)
    )
    if job is None:
        raise HTTPException(status_code=404, detail="No se encontró ese trabajo.")
    return job


def _job_response(job: ProcessingJob) -> JobResponse:
    return JobResponse(
        id=job.id,
        image_id=job.image_id,
        status=job.status,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        status_url=f"/jobs/{job.id}",
        result_url=f"/jobs/{job.id}/result" if job.status == "succeeded" else None,
    )


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: UUID, db: DatabaseSession, user: CurrentUser) -> JobResponse:
    return _job_response(_get_owned_job(db, user.id, job_id))


@router.get("/{job_id}/result")
def get_job_result(
    job_id: UUID,
    request: Request,
    db: DatabaseSession,
    user: CurrentUser,
) -> FileResponse:
    job = _get_owned_job(db, user.id, job_id)
    if job.status != "succeeded" or not job.output_path or not job.output_content_type:
        raise HTTPException(
            status_code=409, detail="El resultado estará disponible cuando termine el trabajo."
        )
    storage: ImageStorage = request.app.state.storage
    path = storage.resolve(job.output_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="El resultado ya no está disponible.")
    return FileResponse(path, media_type=job.output_content_type, filename=path.name)
