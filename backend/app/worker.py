from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.database import build_engine, build_session_factory
from app.imaging import ImageOperationError, transform_image
from app.models import ImageAsset, ProcessingJob, utcnow
from app.queue import ClaimedJob, claim_next_job, mark_job_failed, mark_job_succeeded
from app.settings import Settings
from app.storage import ImageStorage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("image-worker")


class LeaseHeartbeat:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        claim: ClaimedJob,
        lease_seconds: int,
        interval_seconds: int,
    ):
        self.session_factory = session_factory
        self.claim = claim
        self.lease_seconds = lease_seconds
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def __enter__(self) -> LeaseHeartbeat:
        if self.interval_seconds > 0:
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=max(1, self.interval_seconds * 2))

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval_seconds):
            try:
                with self.session_factory() as session:
                    result = session.execute(
                        update(ProcessingJob)
                        .where(
                            ProcessingJob.id == self.claim.id,
                            ProcessingJob.status == "processing",
                            ProcessingJob.lease_token == self.claim.lease_token,
                        )
                        .values(
                            lease_until=utcnow() + timedelta(seconds=self.lease_seconds),
                            updated_at=utcnow(),
                        )
                    )
                    session.commit()
                    if result.rowcount != 1:
                        self.stop_event.set()
                        return
            except Exception:
                logger.exception("No se pudo renovar la reserva del trabajo %s", self.claim.id)


def _load_input(
    session_factory: sessionmaker[Session], claim: ClaimedJob, storage: ImageStorage
) -> tuple[Path, list[dict[str, object]]]:
    with session_factory() as session:
        job = session.get(ProcessingJob, claim.id)
        if job is None or job.status != "processing" or job.lease_token != claim.lease_token:
            raise LeaseLostError("El worker ya no posee la reserva del trabajo.")
        image = session.scalar(
            select(ImageAsset).where(
                ImageAsset.id == claim.image_id,
                ImageAsset.user_id == claim.user_id,
            )
        )
        if image is None:
            raise FileNotFoundError("El original no está registrado.")
        original_path = storage.resolve(image.original_path)
        if not original_path.is_file():
            raise FileNotFoundError("El archivo original ya no está disponible.")
        operations = json.loads(job.operations_json)
    return original_path, operations


class LeaseLostError(RuntimeError):
    pass


def run_claimed_job(
    claim: ClaimedJob,
    session_factory: sessionmaker[Session],
    storage: ImageStorage,
    lease_seconds: int = 60,
    heartbeat_seconds: int = 15,
) -> bool:
    try:
        with LeaseHeartbeat(session_factory, claim, lease_seconds, heartbeat_seconds):
            original_path, operations = _load_input(session_factory, claim, storage)
            source = original_path.read_bytes()
            result, content_type, (width, height) = transform_image(source, operations)
            output_path = storage.save_result(
                claim.user_id,
                claim.id,
                content_type,
                result,
                claim.lease_token,
            )
            with session_factory() as session:
                completed = mark_job_succeeded(
                    session,
                    claim,
                    output_path,
                    content_type,
                    len(result),
                    width,
                    height,
                )
            return completed
    except LeaseLostError:
        logger.info("Se perdió la reserva del trabajo %s; se descarta este resultado", claim.id)
        return False
    except ImageOperationError as error:
        with session_factory() as session:
            mark_job_failed(session, claim, "transform_invalid", str(error), permanent=True)
        return False
    except FileNotFoundError as error:
        with session_factory() as session:
            mark_job_failed(session, claim, "original_missing", str(error), permanent=True)
        return False
    except Exception:
        logger.exception("Error temporal procesando el trabajo %s", claim.id)
        with session_factory() as session:
            mark_job_failed(
                session,
                claim,
                "processing_error",
                "Ocurrió un error temporal al procesar la imagen. El trabajo volverá a intentarse.",
            )
        return False


def run_worker(
    settings: Settings,
    session_factory: sessionmaker[Session] | None = None,
    storage: ImageStorage | None = None,
    once: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    engine = None
    if session_factory is None:
        engine = build_engine(settings)
        session_factory = build_session_factory(engine)
    storage = storage or ImageStorage(settings.data_dir)
    try:
        logger.info("Worker listo; reserva de %s segundos", settings.worker_lease_seconds)
        while True:
            with session_factory() as session:
                claim = claim_next_job(session, lease_seconds=settings.worker_lease_seconds)
            if claim is None:
                if once:
                    return
                sleep(settings.worker_poll_seconds)
                continue
            logger.info("Procesando trabajo %s (intento %s)", claim.id, claim.attempt_count)
            if settings.worker_demo_pause_seconds > 0:
                logger.info(
                    "Pausa de demostración durante %s segundos", settings.worker_demo_pause_seconds
                )
                sleep(settings.worker_demo_pause_seconds)
            run_claimed_job(
                claim,
                session_factory,
                storage,
                lease_seconds=settings.worker_lease_seconds,
                heartbeat_seconds=settings.worker_heartbeat_seconds,
            )
            if once:
                return
    finally:
        if engine is not None:
            engine.dispose()


def main() -> None:
    run_worker(Settings())


if __name__ == "__main__":
    main()
