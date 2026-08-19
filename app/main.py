from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.websocket import router as websocket_router
from app.core.config import Settings, get_settings
from app.core.container import AppContainer
from app.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    container = AppContainer(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await container.start()
        try:
            yield
        finally:
            await container.close()

    application = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    application.state.container = container
    application.include_router(health_router)
    application.include_router(websocket_router)
    return application


app = create_app()
