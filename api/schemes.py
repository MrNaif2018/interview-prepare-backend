from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, ClassVar

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, EmailStr, Field, PlainSerializer, field_validator, model_validator

from api.types import StrEnum

DecimalAsFloat = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]


# Base setup for all models
class WorkingMode(StrEnum):
    UNSET = "unset"
    CREATE = "create"
    UPDATE = "update"
    DISPLAY = "display"  # no restrictions


def iter_attributes(obj):  # to do the from_attributes job because pydantic doesn't do it before validator
    for k in dir(obj):
        if not k.startswith("_"):
            v = getattr(obj, k)
            if not callable(v):
                yield k, v


class BaseModel(PydanticBaseModel):
    MODE: ClassVar[str] = WorkingMode.UNSET

    @model_validator(
        mode="wrap"
    )  # TODO: wrap used here due to pydantic bug: https://github.com/pydantic/pydantic/issues/10135
    @classmethod
    def remove_hidden(cls, values, handler):
        if cls.MODE == WorkingMode.UNSET:  # pragma: no cover
            raise ValueError("Base model should not be used directly")
        if not isinstance(values, dict):
            values = {k: v for k, v in iter_attributes(values)}
        if cls.MODE == WorkingMode.DISPLAY:
            values = {k: v for k, v in values.items() if v != ""}
        else:
            # We also skip empty strings (to trigger defaults) as that's what frontend sends
            values = {k: v for k, v in values.items() if k in cls.model_json_schema()["properties"] and v != ""}
        return handler(values)

    @staticmethod
    def schema_extra(schema: dict, cls):
        properties = dict()
        if cls.MODE != WorkingMode.DISPLAY:
            for k, v in schema.get("properties", {}).items():
                hidden_create = v.get("hidden_create", v.get("hidden", False))
                hidden_update = v.get("hidden_update", v.get("hidden", False))
                if (
                    cls.MODE == WorkingMode.CREATE
                    and not hidden_create
                    or cls.MODE == WorkingMode.UPDATE
                    and not hidden_update
                ):
                    properties[k] = v
            schema["properties"] = properties

    model_config = ConfigDict(json_schema_extra=schema_extra)


class CreateModel(BaseModel):
    MODE: ClassVar[str] = WorkingMode.CREATE


class UpdateModel(BaseModel):
    MODE: ClassVar[str] = WorkingMode.UPDATE


class DisplayModel(BaseModel):
    MODE: ClassVar[str] = WorkingMode.DISPLAY


class CreatedMixin(BaseModel):
    metadata: dict[str, Any] = {}
    created: datetime = Field(
        None, json_schema_extra={"hidden": True}, validate_default=True
    )  # set by validator due to circular imports

    @field_validator("created", mode="before")
    @classmethod
    def set_created(cls, v):
        from api.utils.time import now

        return v or now()


# Users
class UserPreferences(DisplayModel):
    pass


class BaseUser(CreatedMixin):
    email: EmailStr
    settings: UserPreferences = UserPreferences()
    permissions: list[str] = []


class CreateUser(CreateModel, BaseUser):
    password: str


class User(UpdateModel, BaseUser):
    password: str


class DisplayUser(DisplayModel, BaseUser):
    id: str


# Tokens
class HTTPCreateToken(CreatedMixin):
    scopes: list[str] = []


class HTTPCreateLoginToken(CreateModel, HTTPCreateToken):
    email: EmailStr = ""
    password: str = ""


class CreateDBToken(DisplayModel, HTTPCreateToken):
    user_id: str


class DisplayToken(CreateDBToken):
    id: str


# Auth stuff
class ChangePassword(UpdateModel):
    old_password: str
    password: str
    logout_all: bool = False


# Misc schemes


class BatchSettings(DisplayModel):
    ids: list[str]
    command: str
    options: dict | None = {}


class EventSystemMessage(DisplayModel):
    event: str
    data: dict
