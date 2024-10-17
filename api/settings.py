import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from api import db


class Settings(BaseSettings):
    db_name: str = Field("interviewprepare", validation_alias="DB_DATABASE")
    db_user: str = Field("postgres", validation_alias="DB_USER")
    db_password: str = Field("", validation_alias="DB_PASSWORD")
    db_host: str = Field("127.0.0.1", validation_alias="DB_HOST")
    db_port: int = Field(5432, validation_alias="DB_PORT")
    openapi_path: str | None = Field(None, validation_alias="OPENAPI_PATH")
    api_title: str = Field("Interview prepare", validation_alias="API_TITLE")

    model_config = SettingsConfigDict(env_file="conf/.env", extra="ignore")

    @property
    def connection_str(self):
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    async def create_db_engine(self):
        return await db.db.set_bind(self.connection_str, min_size=1, loop=asyncio.get_running_loop())

    async def shutdown_db_engine(self):
        await db.db.pop_bind().close()

    @asynccontextmanager
    async def with_db(self):
        engine = await self.create_db_engine()
        yield engine
        await self.shutdown_db_engine()

    async def init(self):
        await self.create_db_engine()

    async def shutdown(self):
        await self.shutdown_db_engine()


settings_ctx = ContextVar("settings")

settings: Settings


def __getattr__(name):
    if name == "settings":
        return settings_ctx.get()
    raise AttributeError(f"module {__name__} has no attribute {name}")
