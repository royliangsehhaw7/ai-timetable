import logging
from core.deps import AgentDeps
from core.models import TimetableSlot, SchedulingFailure
from blackboard.board import Blackboard
from agents.room_agent import room_agent
from agents.lecturer_agent import lecturer_agent
from tools.get_data import get_courses, get_rooms, get_lecturers, get_policy

logger = logging.getLogger(__name__)

# maximum number of consecutive failures before the orchestrator
# gives up entirely. this is a safety net against infinite loops
# when the data makes a complete timetable impossible
# e.g. more courses than rooms x days can accommodate
MAX_RETRIES = 5


class Orchestrator:
    """
    Central controller for the timetable scheduling process.
    Implements the Mediator pattern — the only component that calls agents.
    Implements the Blackboard pattern — the only component that writes to the board.
    Implements the Reflexion pattern — checks board state after every write and self-corrects.
    This is a plain Python class, not a pydantic-ai Agent. No LLM is involved here.
    All decisions made by the orchestrator are deterministic and rule-based.
    """

    def __init__(self):
        # blackboard is created here and owned by the orchestrator for the
        # entire lifetime of the scheduling run. no other component holds
        # a reference to it — agents access it read-only via AgentDeps
        self.board = Blackboard()


    def load_data(self):
        """
        Loads all source entities from the database layer into the Blackboard.
        Called once at the start of run() before the control loop begins.
        This is the only place get_* tool functions are called — keeping
        data loading separate from scheduling logic (SRP).
        """
        courses = get_courses()
        rooms = get_rooms()
        lecturers = get_lecturers()
        policy = get_policy()

        # board.load() populates all fields and initialises the unscheduled
        # list with all courses — the control loop will drain this list
        self.board.load(courses, rooms, lecturers, policy)

        logger.info(
            f"Data loaded — {len(courses)} courses, {len(rooms)} rooms, "
            f"{len(lecturers)} lecturers, "
            f"school days: {policy.school_days}"
        )


    def check_conflicts(self):
        """
        Reflexion check — scans the entire draft_slots list for clashes.
        Called after every write_slot() to verify the board is still valid.

        Checks two clash conditions:
          1. Room clash   — same room assigned to two courses on the same day
          2. Lecturer clash — same lecturer assigned to two courses on the same day

        Uses a nested loop comparing every slot pair (i, j) where j > i
        to avoid duplicate comparisons. Writes conflict messages to the board
        via log_conflict() — never raises exceptions here.

        The orchestrator reads board.has_conflicts() after this call
        to decide whether to undo the last write and defer the course.
        """
        # clear previous conflict messages before each fresh check
        # without this, old resolved conflicts would persist and
        # has_conflicts() would always return True after the first clash
        self.board.clear_conflicts()

        for i in range(len(self.board.draft_slots)):
            for j in range(i + 1, len(self.board.draft_slots)):
                slot_a = self.board.draft_slots[i]
                slot_b = self.board.draft_slots[j]

                # only compare slots on the same day —
                # the same room or lecturer is allowed on different days
                if slot_a.day == slot_b.day:

                    # room clash — two courses sharing the same room on the same day
                    if slot_a.room == slot_b.room:
                        message = (
                            f"Room clash: {slot_a.room} assigned to both "
                            f"'{slot_a.course}' and '{slot_b.course}' on {slot_a.day}"
                        )
                        self.board.log_conflict(message)
                        logger.warning(message)

                    # lecturer clash — same lecturer teaching two courses on the same day
                    if slot_a.lecturer == slot_b.lecturer:
                        message = (
                            f"Lecturer clash: {slot_a.lecturer} assigned to both "
                            f"'{slot_a.course}' and '{slot_b.course}' on {slot_a.day}"
                        )
                        self.board.log_conflict(message)
                        logger.warning(message)


    async def run(self):
        """
        Main control loop — the heart of the orchestrator.

        This is NOT a pipeline. The loop does not execute a fixed sequence of steps.
        Instead it continuously asks: 'what does the board tell me right now?'
        and decides what to do next based on current state.

        The goal condition is board.is_complete() — all courses have a slot.
        The loop runs until the goal is met or MAX_RETRIES is exceeded.

        On every iteration:
          1. Ask the board what to work on next (next unscheduled course)
          2. Ask the board for a valid available day
          3. Call room_agent — get a suitable room suggestion
          4. Call lecturer_agent — get a suitable lecturer suggestion
          5. Write the slot to the board
          6. Run reflexion check — verify the board is still conflict-free
          7. On any failure at steps 2-6 — defer the course and loop back to 1

        retry_count resets to zero after every successful slot write.
        This means MAX_RETRIES is a consecutive failure limit, not a global one.
        """
        self.load_data()

        # consecutive failure counter — resets on every successful slot
        retry_count = 0

        while not self.board.is_complete():

            # safety net — if the system cannot make progress after MAX_RETRIES
            # consecutive attempts, the data likely makes a solution impossible
            if retry_count > MAX_RETRIES:
                logger.error(
                    f"Max retries ({MAX_RETRIES}) exceeded — "
                    f"scheduling cannot be completed"
                )
                raise Exception(
                    f"Scheduling failed after {MAX_RETRIES} consecutive retries. "
                    f"Check failures: {self.board.failures}"
                )

            # --- step 1: get next course to schedule ---
            # board maintains the unscheduled list — orchestrator never tracks this itself
            course = self.board.get_next_unscheduled_course()
            logger.info(f"Attempting to schedule: '{course.name}' "
                       f"(requires_lab={course.requires_lab})")

            # --- step 2: get a valid available day ---
            # board checks policy.school_days AND verifies at least one free
            # room and one free lecturer exist on that day before returning it.
            # orchestrator never assumes or hardcodes which days are valid.
            day = self.board.get_available_day()

            if day is None:
                # no day has both a free room and a free lecturer —
                # this course cannot be scheduled right now
                logger.warning(
                    f"No available day found for '{course.name}' — deferring"
                )
                failure = SchedulingFailure(
                    course=course.name,
                    agent="orchestrator",
                    day="none",
                    reason="No valid day with both a free room and free lecturer"
                )
                self.board.log_failure(failure)
                self.board.defer_course(course)
                retry_count += 1
                continue  # loop back — do not proceed without a valid day

            logger.info(f"Target day for '{course.name}': {day}")

            # ask the board for full Room and Lecturer objects on this day —
            # agents need is_lab and subjects fields to reason about suitability,
            # not just names. this is why get_free_* returns full objects.
            free_rooms = self.board.get_free_rooms_on_day(day)
            free_lecturers = self.board.get_free_lecturers_on_day(day)

            # package the board into deps — agents receive it read-only.
            # the same deps instance is reused for both agent calls on this iteration
            deps = AgentDeps(board=self.board)

            # --- step 3: call room_agent ---
            # the prompt gives the agent everything it needs to reason:
            # course name, lab requirement, and the list of free rooms with
            # their is_lab flags. the agent uses check_room tool to verify
            # its chosen room is still free before committing to it.
            logger.info(f"Calling room_agent for '{course.name}' on {day}")

            room_prompt = (
                f"Find a suitable room for course '{course.name}'. "
                f"Requires lab: {course.requires_lab}. "
                f"Available rooms on {day}: "
                f"{[(r.name, r.is_lab) for r in free_rooms]}. "
                f"Pick the most suitable room and verify it is free "
                f"using the check_room tool."
            )

            room_result = await room_agent.run(room_prompt, deps=deps)

            if not room_result.data.success:
                # agent found no suitable room — log it and try this course later
                logger.warning(
                    f"room_agent could not assign a room for '{course.name}' "
                    f"on {day}: {room_result.data.reason}"
                )
                failure = SchedulingFailure(
                    course=course.name,
                    agent="room_agent",
                    day=day,
                    reason=room_result.data.reason
                )
                self.board.log_failure(failure)
                self.board.defer_course(course)
                retry_count += 1
                continue  # loop back — do not call lecturer_agent without a room

            logger.info(
                f"room_agent assigned '{room_result.data.room}' "
                f"to '{course.name}' — {room_result.data.reason}"
            )

            # --- step 4: call lecturer_agent ---
            # same pattern as room_agent. the prompt gives the agent
            # course name and free lecturers with their subjects lists.
            # the agent matches subjects against course name to find
            # a qualified lecturer — this is the genuine LLM reasoning task.
            logger.info(f"Calling lecturer_agent for '{course.name}' on {day}")

            lecturer_prompt = (
                f"Find a suitable lecturer for course '{course.name}'. "
                f"Available lecturers on {day}: "
                f"{[(l.name, l.subjects) for l in free_lecturers]}. "
                f"Pick the lecturer whose subjects include '{course.name}' "
                f"and verify they are free using the check_lecturer tool."
            )

            lecturer_result = await lecturer_agent.run(lecturer_prompt, deps=deps)

            if not lecturer_result.data.success:
                # agent found no suitable lecturer — log and defer
                logger.warning(
                    f"lecturer_agent could not assign a lecturer for '{course.name}' "
                    f"on {day}: {lecturer_result.data.reason}"
                )
                failure = SchedulingFailure(
                    course=course.name,
                    agent="lecturer_agent",
                    day=day,
                    reason=lecturer_result.data.reason
                )
                self.board.log_failure(failure)
                self.board.defer_course(course)
                retry_count += 1
                continue  # loop back — do not write an incomplete slot

            logger.info(
                f"lecturer_agent assigned '{lecturer_result.data.lecturer}' "
                f"to '{course.name}' — {lecturer_result.data.reason}"
            )

            # --- step 5: write slot to board ---
            # orchestrator is the ONLY writer to the board.
            # both agents returned success — now commit the slot.
            slot = TimetableSlot(
                day=day,
                course=course.name,
                room=room_result.data.room,
                lecturer=lecturer_result.data.lecturer
            )
            self.board.write_slot(slot)
            logger.info(
                f"Slot written — {day} | {course.name} | "
                f"{slot.room} | {slot.lecturer}"
            )

            # --- step 6: reflexion check ---
            # now that the slot is written, inspect the entire board for clashes.
            # this catches any conflict that slipped through — e.g. a race condition
            # between what the board reported as free and what was actually written.
            # if a conflict is found, the last slot is removed and the course
            # is deferred — the board is restored to its pre-write state.
            self.check_conflicts()

            if self.board.has_conflicts():
                logger.warning(
                    f"Reflexion detected conflict after writing slot "
                    f"for '{course.name}' — undoing and deferring"
                )
                self.board.remove_last_slot()  # undo the write
                self.board.defer_course(course)
                retry_count += 1
                continue  # loop back — board restored to clean state

            # --- slot is clean and conflict-free ---
            # only now is the course permanently removed from the unscheduled list.
            # defer_course() was never called so it is still at the front —
            # remove it explicitly here.
            self.board.unscheduled.remove(course)

            # reset consecutive failure counter — progress was made
            retry_count = 0

            logger.info(
                f"'{course.name}' successfully scheduled. "
                f"Remaining: {len(self.board.unscheduled)} courses"
            )

        # goal achieved — all courses have a slot
        logger.info("All courses scheduled — timetable complete")
        return self.board.get_final_timetable()