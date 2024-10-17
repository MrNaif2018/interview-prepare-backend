from fastapi import HTTPException
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from starlette.requests import Request
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from api import models, utils

pwd_context = PasswordHash((BcryptHasher(),))


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


async def authenticate_user(email: str, password: str):
    user = await utils.database.get_object(
        models.User, custom_query=models.User.query.where(models.User.email == email), raise_exception=False
    )
    if not user:
        return False, 404
    if not verify_password(password, user.hashed_password):
        return False, 401
    return user, 200


oauth_kwargs = {
    "tokenUrl": "/token/oauth2",
    "scopes": {
        "admin_access": "Full access to the system",
        "full_control": "Full control over what current user has",
    },
}

bearer_description = """Token authorization. Get a token by sending a POST request to `/token` endpoint (JSON-mode, preferred)
or `/token/oauth2` OAuth2-compatible endpoint.
Ensure to use only those permissions that your app actually needs. `full_control` gives access to all permissions of a user
To authorize, send an `Authorization` header with value of `Bearer <token>` (replace `<token>` with your token)
"""
optional_bearer_description = "Same as Bearer, but not required. Logic for unauthorized users depends on current endpoint"


def get_authenticate_value(scopes):
    return f'Bearer scope="{" ".join(scopes)}"' if scopes else "Bearer"


def check_permissions(user, token, scopes):
    authenticate_value = get_authenticate_value(scopes)
    available_permissions = set(user.permissions)
    actual_scopes = set(token.scopes) if token else set(scopes)
    if "full_control" in actual_scopes:
        actual_scopes = available_permissions
    else:
        actual_scopes &= available_permissions
    if "admin_access" in actual_scopes:
        return
    forbidden_exception = HTTPException(
        status_code=HTTP_403_FORBIDDEN,
        detail="Not enough permissions",
        headers={"WWW-Authenticate": authenticate_value},
    )
    for scope in scopes:
        if scope == "full_control":
            continue
        if scope not in actual_scopes:
            raise forbidden_exception


class AuthDependency(OAuth2PasswordBearer):
    def __init__(self, enabled: bool = True, token_required: bool = True, token: str | None = None, return_token=False):
        self.enabled = enabled
        self.return_token = return_token
        self.token = token
        super().__init__(
            **oauth_kwargs,
            auto_error=token_required,
            scheme_name="Bearer" if token_required else "BearerOptional",
            description=bearer_description if token_required else optional_bearer_description,
        )

    async def _process_request(self, request: Request, security_scopes: SecurityScopes):
        if not self.enabled:
            if self.return_token:  # pragma: no cover
                return None, None
            return None
        authenticate_value = get_authenticate_value(security_scopes.scopes)
        token: str = self.token if self.token else await super().__call__(request)
        exc = HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": authenticate_value},
        )
        if not token:
            raise exc
        data = (
            await models.User.join(models.Token)
            .select(models.Token.id == token)
            .gino.load((models.User, models.Token))
            .first()
        )
        if data is None:
            raise exc
        user, token = data  # first validate data, then unpack
        check_permissions(user, token, security_scopes.scopes)
        await user.load_data()
        if self.return_token:
            return user, token
        return user

    async def __call__(self, request: Request, security_scopes: SecurityScopes):
        try:
            return await self._process_request(request, security_scopes)
        except HTTPException:
            if self.auto_error:
                raise
            if self.return_token:
                return None, None
            return None


auth_dependency = AuthDependency()
optional_auth_dependency = AuthDependency(token_required=False)
