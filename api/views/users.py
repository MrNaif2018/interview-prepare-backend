from fastapi import APIRouter, HTTPException, Request, Security
from sqlalchemy import select

from api import crud, models, schemes, utils
from api.db import db

router = APIRouter(tags=["users"])


@router.get("/me", response_model=schemes.DisplayUser)
async def get_me(user: models.User = Security(utils.authorization.auth_dependency)):
    return user


@router.post("/me/settings", response_model=schemes.DisplayUser)
async def set_settings(
    settings: schemes.UserPreferences,
    user: models.User = Security(utils.authorization.auth_dependency, scopes=["full_control"]),
):
    await user.set_json_key("settings", settings)
    return user


class CreateUserWithToken(schemes.DisplayUser):
    token: str | None


async def user_count(merchant_id: str):
    return await select([db.func.count()]).where(models.User.merchant_id == merchant_id).gino.scalar()


async def create_user(
    request: Request,
    model: schemes.CreateUser,
    auth_user: models.User | None = Security(utils.authorization.optional_auth_dependency, scopes=[]),
):
    user = await utils.database.create_object(models.User, model)
    data = schemes.DisplayUser.model_validate(user).model_dump()
    token = await utils.database.create_object(models.Token, schemes.CreateDBToken(scopes=["full_control"], user_id=user.id))
    data["token"] = token.id
    return data


@router.post("/password")
async def change_password(
    data: schemes.ChangePassword,
    user: models.User = Security(utils.authorization.auth_dependency, scopes=["token_management"]),
):
    if not utils.authorization.verify_password(data.old_password, user.hashed_password):
        raise HTTPException(422, "Invalid password")
    await crud.users.change_password(user, data.password, data.logout_all)
    return True


utils.routing.ModelView.register(
    router,
    "/",
    models.User,
    schemes.User,
    schemes.CreateUser,
    schemes.DisplayUser,
    request_handlers={"post": create_user},
    response_models={"post": CreateUserWithToken},
    scopes={
        "get_all": ["admin_access"],
        "get_count": ["admin_access"],
        "get_one": ["admin_access"],
        "post": [],
        "patch": ["admin_access"],
        "delete": ["admin_access"],
    },
)
