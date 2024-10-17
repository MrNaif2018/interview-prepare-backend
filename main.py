import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.requests import HTTPConnection
from starlette.middleware.cors import CORSMiddleware

from api import settings as settings_module
from api.settings import Settings
from api.views import router


class RawContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        request = HTTPConnection(scope, receive)
        token = settings_module.settings_ctx.set(request.app.settings)
        try:
            await self.app(scope, receive, send)
        finally:
            settings_module.settings_ctx.reset(token)


def get_app():
    settings = Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.ctx_token = settings_module.settings_ctx.set(app.settings)  # for events context
        await settings.init()
        yield
        await app.settings.shutdown()
        settings_module.settings_ctx.reset(app.ctx_token)

    app = FastAPI(
        title=settings.api_title,
        version="1.0.0",
        redoc_url="/",
        docs_url="/swagger",
        lifespan=lifespan,
    )
    app.settings = settings
    app.include_router(router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    app.add_middleware(RawContextMiddleware)

    if settings.openapi_path:
        with open(settings.openapi_path) as f:
            app.openapi_schema = json.loads(f.read())
    return app


app = get_app()
