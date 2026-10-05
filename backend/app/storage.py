from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import UUID


class ImageStorage:
    extensions = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()

    def save_original(self, user_id: UUID, image_id: UUID, content_type: str, data: bytes) -> str:
        extension = self._extension(content_type)
        relative_path = Path("originals") / str(user_id) / f"{image_id}.{extension}"
        self._atomic_write(relative_path, data, suffix=f".{extension}.tmp")
        return relative_path.as_posix()

    def save_result(
        self, user_id: UUID, job_id: UUID, content_type: str, data: bytes, lease_token: str
    ) -> str:
        extension = self._extension(content_type)
        relative_path = Path("results") / str(user_id) / f"{job_id}.{extension}"
        self._atomic_write(relative_path, data, suffix=f".{lease_token}.tmp")
        return relative_path.as_posix()

    def resolve(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("La ruta solicitada está fuera del almacenamiento de imágenes.")
        return path

    def remove(self, relative_path: str) -> None:
        self.resolve(relative_path).unlink(missing_ok=True)

    def _atomic_write(self, relative_path: Path, data: bytes, suffix: str) -> None:
        destination = self.resolve(relative_path.as_posix())
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.stem}.", suffix=suffix, dir=destination.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_name, destination)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise

    @staticmethod
    def _extension(content_type: str) -> str:
        try:
            return ImageStorage.extensions[content_type]
        except KeyError as error:
            raise ValueError("El formato de imagen no está permitido.") from error
