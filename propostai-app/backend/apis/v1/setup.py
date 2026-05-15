"""
Setup / Onboarding endpoints.
"""
from fastapi import APIRouter, Depends

from core.security import get_current_user
from models.user import User

router = APIRouter()


@router.get("/status")
async def setup_status(user: User = Depends(get_current_user)):
    return {
        "completed": True,
        "current_step": "done",
        "steps": {
            "company": True,
            "users": True,
            "template": True,
            "branding": True,
            "agent": True,
        },
    }


@router.post("/step")
async def setup_step(body: dict, user: User = Depends(get_current_user)):
    return {"ok": True, "step": body.get("step")}


@router.post("/complete")
async def setup_complete(user: User = Depends(get_current_user)):
    return {"ok": True, "completed": True}
