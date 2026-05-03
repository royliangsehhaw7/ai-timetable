from pydantic_ai import Agent, RunContext
from core.deps import AgentDeps
from core.models import RoomSuggestion


room_agent = Agent(
    model="google/gemini-2.5-flash",
    deps_type=AgentDeps,
    result_type=RoomSuggestion,
    system_prompt=(
        "You are a room assignment assistant. "
        "You will be given a course name, whether it requires a lab, "
        "and a list of free rooms. "
        "Your job is to pick the most suitable room for the course. "
        "If the course requires a lab, you must pick a room where is_lab is True. "
        "If no suitable room exists, return success=False with a clear reason. "
        "Always populate the reason field."
    )
)


@room_agent.tool
async def check_room(
    ctx: RunContext[AgentDeps],
    room_name: str,
    day: str
) -> str:
    # tool lets the agent verify a specific room is still free
    # before committing to it in the result
    used_rooms = ctx.deps.board.get_used_rooms_on_day(day)

    if room_name in used_rooms:
        return f"{room_name} is already taken on {day}"

    return f"{room_name} is free on {day}"