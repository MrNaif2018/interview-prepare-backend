from fastapi import APIRouter

from api.views.token import router as token_router
from api.views.users import router as user_router

router = APIRouter()

# We separate views by object type

# Regular routes
router.include_router(user_router, prefix="/users")


# Authorization
router.include_router(token_router, prefix="/token")
