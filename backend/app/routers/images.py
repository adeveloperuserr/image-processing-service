from __future__ import annotations

import hashlib
import json
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, get_settings
from app.imaging import ImageOperationError, inspect_image
from app.models import ImageAsset, ProcessingJob, User, utcnow
from app.schemas import ImagePage, ImageResponse, TransformAccepted, TransformRequest
from app.settings import Settings
from app.storage import ImageStorage

router = APIRouter(prefix="/images", tags=["imágenes"])
DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
FORMAT_DETAILS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}


def _image_response(image: ImageAsset) -> ImageResponse:
    return ImageResponse(
        id=image.id,
        original_name=image.original_name,
        content_type=image.content_type,
        size_bytes=image.size_bytes,
        width=image.width,
        height=image.height,
        created_at=image.created_at,
        original_url=f"/images/{image.id}/original",
    )


def _get_owned_image(db: Session, user_id: UUID, image_id: UUID) -> ImageAsset:
    image = db.scalar(
        select(ImageAsset).where(ImageAsset.id == image_id, ImageAsset.user_id == user_id)
    )
    if image is None:
        raise HTTPException(status_code=404, detail="No se encontró esa imagen.")
    return image


def _accepted(job: ProcessingJob) -> TransformAccepted:
    result_url = f"/jobs/{job.id}/result" if job.status == "succeeded" else None
    return TransformAccepted(
        id=job.id,
        image_id=job.image_id,
        status=job.status,
        attempt_count=job.attempt_count,
        status_url=f"/jobs/{job.id}",
        result_url=result_url,
    )


@router.post("", response_model=ImageResponse, status_code=status.HTTP_201_CREATED)
async def upload_image(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    db: DatabaseSession,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ImageResponse:
    content = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="La imagen supera el límite de 20 MB.")
    try:
        image_format, (width, height) = inspect_image(content)
    except ImageOperationError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error

    content_type, extension = FORMAT_DETAILS[image_format]
    image_id = uuid4()
    storage: ImageStorage = request.app.state.storage
    original_path = storage.save_original(user.id, image_id, content_type, content)
    source_name = (file.filename or "imagen").replace("\\", "/").split("/")[-1]
    safe_name = "".join(character for character in source_name if character.isprintable())[:255]
    asset = ImageAsset(
        id=image_id,
        user_id=user.id,
        original_name=safe_name or f"imagen.{extension}",
        original_path=original_path,
        content_type=content_type,
        size_bytes=len(content),
        width=width,
        height=height,
    )
    db.add(asset)
    try:
        db.commit()
    except BaseException:
        db.rollback()
        storage.remove(original_path)
        raise
    db.refresh(asset)
    return _image_response(asset)


@router.get("", response_model=ImagePage)
def list_images(
    db: DatabaseSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> ImagePage:
    base_query = select(ImageAsset).where(ImageAsset.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    images = db.scalars(
        base_query.order_by(ImageAsset.created_at.desc(), ImageAsset.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return ImagePage(
        items=[_image_response(image) for image in images], page=page, limit=limit, total=total
    )


@router.post("/{image_id}/transform", response_model=TransformAccepted, status_code=202)
def request_transform(
    image_id: UUID,
    payload: TransformRequest,
    db: DatabaseSession,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=80)],
) -> TransformAccepted:
    image = _get_owned_image(db, user.id, image_id)
    operations = [operation.model_dump(mode="json") for operation in payload.operations]
    canonical = json.dumps(
        {"image_id": str(image.id), "operations": operations},
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    existing = db.scalar(
        select(ProcessingJob).where(
            ProcessingJob.user_id == user.id,
            ProcessingJob.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(
                status_code=409,
                detail="Usa una clave de idempotencia nueva para cambiar la solicitud.",
            )
        return _accepted(existing)

    job = ProcessingJob(
        id=uuid4(),
        user_id=user.id,
        image_id=image.id,
        operations_json=json.dumps(operations, separators=(",", ":")),
        request_fingerprint=fingerprint,
        idempotency_key=idempotency_key,
        max_attempts=settings.worker_max_attempts,
        status="queued",
        available_at=utcnow(),
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(ProcessingJob).where(
                ProcessingJob.user_id == user.id,
                ProcessingJob.idempotency_key == idempotency_key,
            )
        )
        if existing is None or existing.request_fingerprint != fingerprint:
            raise HTTPException(
                status_code=409, detail="La clave de idempotencia ya está en uso."
            ) from None
        return _accepted(existing)
    db.refresh(job)
    return _accepted(job)


@router.get("/{image_id}", response_model=ImageResponse)
def get_image(image_id: UUID, db: DatabaseSession, user: CurrentUser) -> ImageResponse:
    return _image_response(_get_owned_image(db, user.id, image_id))


@router.get("/{image_id}/original")
def get_original(
    image_id: UUID,
    request: Request,
    db: DatabaseSession,
    user: CurrentUser,
) -> FileResponse:
    image = _get_owned_image(db, user.id, image_id)
    storage: ImageStorage = request.app.state.storage
    path = storage.resolve(image.original_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="El archivo original ya no está disponible.")
    return FileResponse(path, media_type=image.content_type, filename=image.original_name)
