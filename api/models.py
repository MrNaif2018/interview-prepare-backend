import inspect
import secrets
import sys

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from gino.crud import UpdateRequest
from gino.declarative import ModelType
from sqlalchemy.dialects.postgresql import ARRAY

from api import schemes
from api.db import db

# shortcuts
Column = db.Column
Integer = db.Integer
Text = db.Text
Boolean = db.Boolean
Numeric = db.Numeric
DateTime = db.DateTime
Text = db.Text
ForeignKey = db.ForeignKey
JSON = db.JSON
UniqueConstraint = db.UniqueConstraint


async def create_relations(model_id, related_ids, key_info):
    from api import utils

    if key_info.get("one_to_many"):
        data = [
            {key_info["current_id"]: model_id, "id": utils.common.unique_id(), "created": utils.time.now(), **related_id}
            for related_id in related_ids
        ]
    else:
        data = [{key_info["current_id"]: model_id, key_info["related_id"]: related_id} for related_id in related_ids]
    if data:
        await key_info["table"].insert().gino.all(data)


async def delete_relations(model_id, key_info):
    await key_info["table"].delete.where(getattr(key_info["table"], key_info["current_id"]) == model_id).gino.status()


class BaseModelMeta(ModelType):
    def __new__(cls, name, bases, attrs):
        new_class = type.__new__(cls, name, bases, attrs)
        new_class.__namespace__ = attrs
        if hasattr(new_class, "__tablename__"):
            if hasattr(new_class, "TABLE_PREFIX"):  # pragma: no cover
                new_class.__namespace__["__tablename__"] = f"plugin_{new_class.TABLE_PREFIX}_{new_class.__tablename__}"
            if getattr(new_class, "METADATA", True):
                new_class.__namespace__["metadata"] = Column(JSON)
        if new_class.__table__ is None:
            new_class.__table__ = getattr(new_class, "_init_table")(new_class)
        return new_class


class BaseModel(db.Model, metaclass=BaseModelMeta):
    JSON_KEYS: dict = {}
    FKEY_MAPPING: dict = {}

    @property
    def M2M_KEYS(self):
        model_variant = getattr(self, "KEYS", {})
        update_variant = getattr(self._update_request_cls, "KEYS", {})
        return model_variant or update_variant

    async def create_related(self):
        for key in self.M2M_KEYS:
            related_ids = getattr(self, key, [])
            await create_relations(self.id, related_ids, self.M2M_KEYS[key])

    async def add_related(self):
        for key in self.M2M_KEYS:
            key_info = self.M2M_KEYS[key]
            if key_info.get("one_to_many"):
                result = (
                    await key_info["table"]
                    .query.where(getattr(key_info["table"], key_info["current_id"]) == self.id)
                    .gino.all()
                )
                setattr(self, key, result)
            else:
                result = (
                    await key_info["table"]
                    .select(key_info["related_id"])
                    .where(getattr(key_info["table"], key_info["current_id"]) == self.id)
                    .gino.all()
                )
                setattr(self, key, [obj_id for obj_id, in result if obj_id])

    async def delete_related(self):
        for key_info in self.M2M_KEYS.values():
            await delete_relations(self.id, key_info)

    async def add_fields(self):
        for field, scheme in self.JSON_KEYS.items():
            setattr(self, field, self.get_json_key(field, scheme))

    async def load_data(self):
        await self.add_related()
        await self.add_fields()

    async def _delete(self, *args, **kwargs):
        await self.delete_related()
        return await super()._delete(*args, **kwargs)

    @classmethod
    async def create(cls, **kwargs):
        model = await super().create(**kwargs)
        await model.create_related()
        await model.load_data()
        return model

    async def validate(self, kwargs, user=None):
        from api import utils

        fkey_columns = (col for col in self.__table__.columns if col.foreign_keys)
        exc = HTTPException(403, "Access denied: attempt to use objects not owned by current user")
        for col in fkey_columns:
            if col.name in kwargs:
                # we assume i.e. user_id -> User
                table_name = self.FKEY_MAPPING.get(col.name, col.name.replace("_id", "").capitalize())
                check_kwargs = {"raise_exception": False}
                if user:
                    check_kwargs["user"] = user
                if kwargs[col.name] and not await utils.database.get_object(
                    all_tables[table_name], kwargs[col.name], **check_kwargs
                ):
                    raise exc

        for key in self.M2M_KEYS:
            if key in kwargs:
                key_info = self.M2M_KEYS[key]
                if key_info.get("one_to_many"):
                    continue
                related_ids = kwargs[key]
                count = await utils.database.get_scalar(
                    key_info["related_table"]
                    .query.where(key_info["related_table"].user_id == self.user_id)  # TODO: RBAC
                    .where(key_info["related_table"].id.in_(related_ids)),
                    db.func.count,
                    key_info["related_table"].id,
                )
                if count != len(related_ids):
                    raise exc

    @classmethod
    def access_filter(cls, user, query):
        return query

    async def create_access(self, user):
        pass

    @classmethod
    def process_kwargs(cls, kwargs):
        return kwargs

    @classmethod
    def prepare_create(cls, kwargs):
        from api import utils

        kwargs["id"] = utils.common.unique_id()
        if "metadata" not in kwargs and getattr(cls, "METADATA", True):  # pragma: no cover
            kwargs["metadata"] = {}
        return kwargs

    def prepare_edit(self, kwargs):
        kwargs.pop("user", None)  # side effect of access_filter # TODO: maybe no longer needed?
        return kwargs

    def get_json_key(self, key, scheme):
        data = getattr(self, key) or {}
        return scheme(**data)

    async def set_json_key(self, key, scheme):
        # Update only passed values, don't modify existing ones
        json_data = jsonable_encoder(getattr(self, key).model_copy(update=scheme.model_dump(exclude_unset=True)))
        kwargs = {key: json_data}
        await self.update(**kwargs).apply()


# Abstract class to easily implement many-to-many update behaviour


# NOTE: do NOT edit self, but self._instance instead - it is the target model
class RelationshipUpdateRequest(UpdateRequest):
    KEYS: dict

    def update(self, **kwargs):
        self.modified = False
        for key in self.KEYS:
            if key in kwargs:
                setattr(self._instance, key, kwargs.pop(key))
                self.modified = True
        self.empty = not kwargs
        return super().update(**kwargs)

    async def apply(self):
        if self.modified:
            for key in self.KEYS:
                key_info = self.KEYS[key]
                data = getattr(self._instance, key, None)
                if data is None:  # pragma: no cover
                    data = []
                else:
                    await delete_relations(self._instance.id, key_info)
                await create_relations(self._instance.id, data, key_info)
                setattr(self._instance, key, data)
        if not self.empty:
            return await super().apply()


class User(BaseModel):
    __tablename__ = "users"

    JSON_KEYS = {"settings": schemes.UserPreferences}

    id = Column(Text, primary_key=True, index=True)
    email = Column(Text, unique=True, index=True)
    hashed_password = Column(Text)
    permissions = Column(ARRAY(Text))
    created = Column(DateTime(True), nullable=False)
    settings = Column(JSON)

    @classmethod
    def process_kwargs(cls, kwargs):
        from api import utils

        kwargs = super().process_kwargs(kwargs)
        if "password" in kwargs:
            if kwargs["password"] is not None:
                kwargs["hashed_password"] = utils.authorization.get_password_hash(kwargs["password"])
            del kwargs["password"]
        return kwargs


class Question(BaseModel):
    __tablename__ = "questions"

    id = Column(Text, primary_key=True, index=True)
    name = Column(Text)
    question = Column(Text)
    options = Column(ARRAY(Text))
    answer = Column(Text)
    difficulty = Column(Text)
    topic = Column(Text)
    company = Column(Text)
    hints = Column(ARRAY(Text))
    solutions = Column(ARRAY(Text))
    comments = Column(JSON)
    created = Column(DateTime(True), nullable=False)


class Setting(BaseModel):
    __tablename__ = "settings"

    METADATA = False

    id = Column(Text, primary_key=True, index=True)
    name = Column(Text)
    value = Column(Text)
    created = Column(DateTime(True), nullable=False)

    @classmethod
    def prepare_create(cls, kwargs):
        from api import utils

        kwargs = super().prepare_create(kwargs)
        kwargs["created"] = utils.time.now()
        return kwargs


class Token(BaseModel):
    __tablename__ = "tokens"

    id = Column(Text, primary_key=True, index=True)
    user_id = Column(Text, ForeignKey(User.id, ondelete="SET NULL"), index=True)
    scopes = Column(ARRAY(Text))
    created = Column(DateTime(True), nullable=False)

    @classmethod
    def prepare_create(cls, kwargs):
        kwargs = super().prepare_create(kwargs)
        kwargs["id"] = secrets.token_urlsafe()
        return kwargs


all_tables = {
    name: table
    for (name, table) in inspect.getmembers(sys.modules[__name__], inspect.isclass)
    if issubclass(table, BaseModel) and table is not BaseModel
}
