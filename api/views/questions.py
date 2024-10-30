from fastapi import APIRouter, HTTPException, Security
from pydantic import BaseModel

from api import models, schemes, utils

router = APIRouter(tags=["questions"])


class SubmitMessage(BaseModel):
    message: str


class SolveMessage(BaseModel):
    answer: str


@router.post("/{model_id}/comment", response_model=schemes.DisplayQuestion)
async def submit_comment(
    model_id: str, message: SubmitMessage, user: models.User = Security(utils.authorization.auth_dependency, scopes=[])
):
    question = await utils.database.get_object(models.Question, model_id)
    question.comments.append({"email": user.email, "message": message.message})
    await question.update(comments=question.comments).apply()
    return question


@router.post("/{model_id}/solve", response_model=schemes.DisplayQuestion)
async def submit_solve(
    model_id: str, solution: SolveMessage, user: models.User = Security(utils.authorization.auth_dependency, scopes=[])
):
    question = await utils.database.get_object(models.Question, model_id)
    if question.answer != solution.answer:
        raise HTTPException(status_code=400, detail="Wrong answer")
    question.solutions.append(user.email)
    question.solutions = list(set(question.solutions))
    await question.update(solutions=question.solutions).apply()
    return question


utils.routing.ModelView.register(
    router,
    "/",
    models.Question,
    schemes.UpdateQuestion,
    schemes.CreateQuestion,
    schemes.DisplayQuestion,
    scopes={
        "get_all": [],
        "get_count": [],
        "get_one": [],
        "post": ["admin_access"],
        "patch": ["admin_access"],
        "delete": ["admin_access"],
    },
)
