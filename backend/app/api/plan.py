from fastapi import APIRouter
from app.services.ai_planner import create_action_plan
import asyncio

router = APIRouter()

@router.post("/plan")
async def plan_endpoint(instruction: dict):
    """Test endpoint for the AI planner."""
    user_input = instruction.get("instruction", "")
    plan = await create_action_plan(user_input)
    return {"plan": plan}

