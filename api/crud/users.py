from api import models, utils


async def change_password(user, password, logout_all=True):
    await utils.database.modify_object(user, {"password": password})
    if logout_all:
        await models.Token.delete.where(models.Token.user_id == user.id).gino.status()
