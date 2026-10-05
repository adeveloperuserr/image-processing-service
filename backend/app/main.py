from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import build_engine, build_session_factory
from app.routers import auth, images, jobs
from app.settings import Settings
from app.storage import ImageStorage


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    configured_settings = settings or Settings()
    engine: Engine | None = None
    if session_factory is None:
        engine = build_engine(configured_settings)
        session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        configured_settings.data_dir.mkdir(parents=True, exist_ok=True)
        yield
        if engine is not None:
            engine.dispose()

    app = FastAPI(
        title="Image Processing Service",
        description="Carga imágenes, crea trabajos de transformación y consulta su estado.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = configured_settings
    app.state.session_factory = session_factory
    app.state.storage = ImageStorage(configured_settings.data_dir)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )
    app.include_router(auth.router)
    app.include_router(images.router)
    app.include_router(jobs.router)

    @app.get("/health", tags=["sistema"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
