from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(StrictPayload):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(StrictPayload):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserSummary(BaseModel):
    id: UUID
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserSummary


class ResizeOperation(StrictPayload):
    type: Literal["resize"]
    width: int = Field(gt=0, le=8000)
    height: int = Field(gt=0, le=8000)


class CropOperation(StrictPayload):
    type: Literal["crop"]
    x: int = Field(ge=0, le=40000)
    y: int = Field(ge=0, le=40000)
    width: int = Field(gt=0, le=40000)
    height: int = Field(gt=0, le=40000)


class WatermarkOperation(StrictPayload):
    type: Literal["watermark"]
    text: str = Field(min_length=1, max_length=80)
    position: Literal["top-left", "top-right", "bottom-left", "bottom-right", "center"] = (
        "bottom-right"
    )


class FormatOperation(StrictPayload):
    type: Literal["format"]
    format: Literal["jpeg", "jpg", "png", "webp"]


ImageOperation = Annotated[
    ResizeOperation | CropOperation | WatermarkOperation | FormatOperation,
    Field(discriminator="type"),
]


class TransformRequest(StrictPayload):
    operations: list[ImageOperation] = Field(min_length=1, max_length=12)


class ImageResponse(BaseModel):
    id: UUID
    original_name: str
    content_type: str
    size_bytes: int
    width: int
    height: int
    created_at: datetime
    original_url: str


class ImagePage(BaseModel):
    items: list[ImageResponse]
    page: int
    limit: int
    total: int


class JobResponse(BaseModel):
    id: UUID
    image_id: UUID
    status: Literal["queued", "processing", "succeeded", "failed"]
    attempt_count: int
    max_attempts: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    status_url: str
    result_url: str | None = None


class TransformAccepted(BaseModel):
    id: UUID
    image_id: UUID
    status: Literal["queued", "processing", "succeeded", "failed"]
    attempt_count: int
    status_url: str
    result_url: str | None = None


class JobResult(BaseModel):
    job: JobResponse
