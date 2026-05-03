from pydantic_ai import Agent, RunContext
from core.deps import AgentDeps
from core.models import LecturerSuggestion


lecturer_agent = Agent(
    model="google/gemini-2.5-flash",
    deps_type=AgentDeps,
    result_type=LecturerSuggestion,
    system_prompt=(
        "You are a lecturer assignment assistant. "
        "You will be given a course name and a list of free lecturers, "
        "each with their list of subjects they can teach. "
        "Your job is to pick the most suitable lecturer for the course. "
        "The lecturer's subjects list must include the course name. "
        "If no suitable lecturer exists, return success=False with a clear reason. "
        "Always populate the reason field."
    )
)


@lecturer_agent.tool
async def check_lecturer(
    ctx: RunContext[AgentDeps],
    lecturer_name: str,
    day: str
) -> str:
    # tool lets the agent verify a specific lecturer is still free
    # before committing to it in the result
    used_lecturers = ctx.deps.board.get_used_lecturers_on_day(day)

    if lecturer_name in used_lecturers:
        return f"{lecturer_name} is already assigned on {day}"

    return f"{lecturer_name} is free on {day}"