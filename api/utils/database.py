from contextlib import asynccontextmanager, contextmanager
from typing import TypeVar

import asyncpg
from fastapi import HTTPException
from sqlalchemy import and_, distinct

from api import db

ModelType = TypeVar("ModelType")


@contextmanager
def safe_db_write():
    try:
        yield
    except asyncpg.exceptions.IntegrityConstraintViolationError as e:  # pragma: no cover
        raise HTTPException(422, str(e))


def get_kwargs(model, data, additional_kwargs):
    kwargs = data if isinstance(data, dict) else data.model_dump()
    kwargs.update(additional_kwargs)
    return model.process_kwargs(kwargs)


def prepare_create_kwargs(model, data, **additional_kwargs):
    kwargs = get_kwargs(model, data, additional_kwargs)
    kwargs = model.prepare_create(kwargs)
    return kwargs


async def create_object_core(model, kwargs, user):
    model = model(**kwargs)  # Create object instance to allow calling instance methods
    await model.validate(kwargs, user)
    with safe_db_write():
        result = await model.create(**kwargs)
    return result


async def create_object(model: type[ModelType], data, user=None, **additional_kwargs) -> ModelType:
    kwargs = prepare_create_kwargs(model, data, **additional_kwargs)
    model = await create_object_core(model, kwargs, user)
    if user:
        await model.create_access(user)
    return model


async def modify_object(model, data, **additional_kwargs):
    kwargs = get_kwargs(model, data, additional_kwargs)
    kwargs = model.prepare_edit(kwargs)
    await model.validate(kwargs)
    with safe_db_write():
        try:
            await model.update(**kwargs).apply()
        except asyncpg.exceptions.PostgresSyntaxError:  # pragma: no cover
            pass


async def get_object(
    model: type[ModelType],
    model_id=None,
    user=None,
    custom_query=None,
    raise_exception=True,
    load_data=True,
    atomic_update=False,
    fixed_filters={},
) -> ModelType:
    if custom_query is not None:
        query = custom_query
    else:
        query = model.query.where(model.id == model_id)
        if user:
            query = model.access_filter(user, query)
        query = apply_filters(model, query, fixed_filters)
    if atomic_update:
        query = query.with_for_update()
    item = await query.gino.first()
    if not item:
        if raise_exception:
            raise HTTPException(404, f"{model.__name__} with id {model_id} does not exist!")
        return
    if load_data:
        await item.load_data()
    return item


async def get_scalar(query, func, column, use_distinct=True):
    column = distinct(column) if use_distinct else column
    return await query.with_only_columns([func(column)]).order_by(None).gino.scalar() or 0


async def postprocess_func(items):
    for item in items:
        await item.load_data()
    return items


async def paginate_object(model, pagination, user, *args, **kwargs):
    return await pagination.paginate(model, user, postprocess=postprocess_func, *args, **kwargs)


@asynccontextmanager
async def iterate_helper():
    async with db.db.acquire() as conn:
        async with conn.transaction():
            yield


def apply_filters(model, query, filters):
    return query.where(and_(*[getattr(model, k) == v for k, v in filters.items()]))


async def get_objects(model, ids, postprocess=True):  # TODO: maybe use iterate instead?
    data = await model.query.where(model.id.in_(ids)).gino.all()
    if postprocess:
        await postprocess_func(data)
    return data
