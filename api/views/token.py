from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import ValidationError
from starlette.requests import Request

from api import models, schemes, utils

router = APIRouter(tags=["token"])


@router.get("/current", response_model=schemes.DisplayToken)
async def get_current_token(
    auth_data: tuple[models.User, str] = Security(utils.authorization.AuthDependency(return_token=True)),
):
    return auth_data[1]


@router.delete("/{model_id}", response_model=schemes.DisplayToken)
async def delete_token(
    model_id: str,
    user: models.User = Security(utils.authorization.auth_dependency, scopes=["token_management"]),
):
    item = await utils.database.get_object(
        models.Token,
        model_id,
        custom_query=models.Token.query.where(models.Token.user_id == user.id).where(models.Token.id == model_id),
    )
    await item.delete()
    return item


@router.post("/batch")
async def batch_action(
    settings: schemes.BatchSettings,
    user: models.User = Security(utils.authorization.auth_dependency, scopes=["token_management"]),
):  # pragma: no cover
    query = None
    if settings.command == "delete":
        query = models.Token.delete
    if query is None:
        raise HTTPException(status_code=404, detail="Batch command not found")
    query = query.where(models.Token.user_id == user.id).where(models.Token.id.in_(settings.ids))
    await query.gino.status()
    return True


async def validate_credentials(user, token_data):
    if not user:
        user, status = await utils.authorization.authenticate_user(token_data.email, token_data.password)
        if not user:
            raise HTTPException(401, {"message": "Unauthorized", "status": status})
    return user


@router.post("/oauth2")
async def create_oauth2_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_data: None | tuple[models.User | None, str] = Security(
        utils.authorization.AuthDependency(token_required=False, return_token=True)
    ),
):  # pragma: no cover
    try:
        token_data = schemes.HTTPCreateLoginToken(
            email=form_data.username, password=form_data.password, scopes=form_data.scopes
        )
    except ValidationError as e:
        raise HTTPException(422, e.errors())
    return await create_token(token_data, auth_data)


@router.post("")
async def create_token(
    token_data: schemes.HTTPCreateLoginToken | None = schemes.HTTPCreateLoginToken(),
    auth_data: None | tuple[models.User | None, str] = Security(
        utils.authorization.AuthDependency(token_required=False, return_token=True)
    ),
):
    user, token = None, None
    if auth_data:
        user, token = auth_data
    user = await validate_credentials(user, token_data)
    token_data = token_data.model_dump()
    role = await utils.database.get_object(models.Role, user.role, raise_exception=False)
    utils.authorization.check_permissions(user, token, role, token_data["scopes"])
    token_data = schemes.CreateDBToken(**token_data, user_id=user.id).model_dump()
    return await create_token_normal(token_data)


async def create_token_normal(token_data):
    token = await utils.database.create_object(models.Token, token_data)
    return {
        **schemes.DisplayToken.model_validate(token).model_dump(),
        "access_token": token.id,
        "token_type": "bearer",
    }
