import asyncio
from collections.abc import Callable

import asyncpg
from fastapi import Query
from sqlalchemy import Text, and_, or_, text
from starlette.requests import Request

from api import utils
from api.db import db


def get_all_columns_filter(model, text):
    return [
        getattr(model, m.key).cast(Text).op("~*")(text)  # NOTE: not cross-db, postgres case-insensitive regex
        for m in model.__table__.columns
    ]


class Pagination:
    default_offset = 0
    default_limit = 5
    max_offset = None
    max_limit = 1000

    def __init__(
        self,
        request: Request,
        offset: int = Query(default=default_offset, ge=0, le=max_offset),
        limit: int = Query(default=default_limit, ge=-1, le=max_limit),
        query: str = Query(default=""),
        multiple: bool = Query(default=False),
        sort: str = Query(default=""),
        desc: bool = Query(default=True),
    ):
        self.request = request
        self.offset = offset
        self.limit = limit
        self.query = utils.common.SearchQuery(query)
        self.multiple = multiple
        if self.multiple:
            self.query.text = self.query.text.replace(",", "|")
        self.sort = sort
        self.desc = desc
        self.desc_s = "desc" if desc else ""
        self.model = None

    def get_previous_url(self) -> str | None:
        if self.offset <= 0:
            return None
        if self.offset - self.limit <= 0:
            return str(self.request.url.remove_query_params(keys=["offset"]))
        return str(self.request.url.include_query_params(limit=self.limit, offset=self.offset - self.limit))

    def get_next_url(self, count) -> str | None:
        if self.offset + self.limit >= count or self.limit == -1:
            return None
        return str(self.request.url.include_query_params(limit=self.limit, offset=self.offset + self.limit))

    async def get_count(self, query) -> int:
        try:
            return await utils.database.get_scalar(query, db.func.count, self.model.id)
        except asyncpg.exceptions.DataError:
            return 0

    async def get_list(self, query) -> list:
        if not self.sort:
            self.sort = "created"
            self.desc_s = "desc"
        query = query.group_by(self.model.id)
        if self.limit != -1:
            query = query.limit(self.limit)
        query = query.order_by(text(f"{self.sort} {self.desc_s}"))
        try:
            return await query.offset(self.offset).gino.all()
        except (asyncpg.exceptions.UndefinedColumnError, asyncpg.exceptions.DataError):
            return []

    def search(self):
        if not self.query:
            return []
        queries = []
        queries.extend(self.query.get_created_filter(self.model))
        for search_filter, value in self.query.filters.items():
            column = getattr(self.model, search_filter, None)
            if column is not None:
                queries.append(column.in_(value))
        full_filters = get_all_columns_filter(self.model, self.query.text)
        queries.append(or_(*full_filters))
        return and_(*queries)

    async def paginate(
        self,
        model,
        user=None,
        postprocess: Callable | None = None,
        count_only=False,
        *args,
        **kwargs,
    ) -> dict | int:
        query = await self.get_queryset(model, user, *args, **kwargs)
        if count_only:
            return await self.get_count(query)
        count, data = await asyncio.gather(self.get_count(query), self.get_list(query))
        if postprocess:
            data = await postprocess(data)
        return {
            "count": count,
            "next": self.get_next_url(count),
            "previous": self.get_previous_url(),
            "result": data,
        }

    def get_base_query(self, model):
        self.model = model
        query = model.query
        queries = self.search()
        query = query.where(queries) if queries != [] else query  # sqlalchemy core requires explicit checks
        return query

    async def get_queryset(
        self,
        model,
        user,
        *args,
        fixed_filters={},
        **kwargs,
    ):
        query = self.get_base_query(model)
        query = model.access_filter(user, query)
        query = utils.database.apply_filters(model, query, fixed_filters)
        return query
