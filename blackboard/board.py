from dataclasses import dataclass, field
from core.models import Course, Room, Lecturer, Policy, TimetableSlot, SchedulingFailure


@dataclass
class Blackboard:
    """
    Shared mutable state for the entire scheduling run.
    Implements the Blackboard pattern — a central information store
    that all components read from, but only the orchestrator writes to.

    Agents access this read-only via AgentDeps and RunContext.
    The orchestrator is the sole writer — it calls write_slot(),
    log_conflict(), log_failure(), and defer_course().

    Every method has one job. No method reaches outside its own
    data to make decisions — that is the orchestrator's responsibility.
    """

    # --- source data ---
    # loaded once at startup via board.load()
    # never modified after loading
    courses:   list[Course]   = field(default_factory=list)
    rooms:     list[Room]     = field(default_factory=list)
    lecturers: list[Lecturer] = field(default_factory=list)
    policy:    Policy         = None

    # --- working state ---
    # mutated only by the orchestrator during the scheduling loop
    draft_slots: list[TimetableSlot]      = field(default_factory=list)
    conflicts:   list[str]                = field(default_factory=list)
    failures:    list[SchedulingFailure]  = field(default_factory=list)

    # --- internal tracking ---
    # unscheduled starts as a copy of all courses.
    # courses are deferred (moved to back) on failure
    # and removed permanently only when a clean slot is written.
    unscheduled: list[Course] = field(default_factory=list)


    def load(self, courses, rooms, lecturers, policy):
        """
        Populates the board with source data.
        Called once by the orchestrator before the control loop starts.
        Initialises unscheduled as a full copy of courses —
        the control loop drains this list toward the goal condition.
        """
        self.courses   = courses
        self.rooms     = rooms
        self.lecturers = lecturers
        self.policy    = policy

        # copy — not a reference. defer_course() mutates this list
        # and must not affect the original courses list
        self.unscheduled = list(courses)


    # --- unscheduled course management ---

    def get_next_unscheduled_course(self):
        """
        Returns the first course in the unscheduled list without removing it.
        The orchestrator removes it permanently only after a clean slot is written.
        Returns None if all courses are scheduled — triggers is_complete().
        """
        if len(self.unscheduled) == 0:
            return None
        return self.unscheduled[0]


    def defer_course(self, course):
        """
        Moves a course from the front to the back of the unscheduled list.
        Called when a course cannot be scheduled on the current attempt —
        room failure, lecturer failure, or conflict detected after write.
        The course will be tried again on the next available iteration.
        This is what prevents the orchestrator from being a pipeline —
        failed courses are retried, not abandoned.
        """
        if course in self.unscheduled:
            self.unscheduled.remove(course)
        self.unscheduled.append(course)


    # --- day selection ---

    def get_available_day(self):
        """
        Returns the first valid school day that still has capacity —
        meaning at least one free room AND at least one free lecturer.

        This is the single place where policy.school_days is enforced.
        The orchestrator never hardcodes or assumes which days are valid —
        it always asks this method.

        Returns None if no day has capacity — the orchestrator will
        log a failure and defer the course when this happens.
        """
        for day in self.policy.school_days:
            used_rooms     = self.get_used_rooms_on_day(day)
            used_lecturers = self.get_used_lecturers_on_day(day)

            free_rooms     = [r for r in self.rooms     if r.name not in used_rooms]
            free_lecturers = [l for l in self.lecturers if l.name not in used_lecturers]

            # day is only valid if both a room AND a lecturer are available —
            # having one without the other makes the day useless for scheduling
            if len(free_rooms) > 0 and len(free_lecturers) > 0:
                return day

        return None


    # --- availability queries ---
    # these are the read-only methods agents access via ctx.deps.board
    # they never modify state — they only report what is currently on the board

    def get_used_rooms_on_day(self, day):
        """
        Returns a list of room names already assigned on the given day.
        Used by get_available_day() and get_free_rooms_on_day() internally,
        and by the check_room tool via agent deps.
        """
        used = []
        for slot in self.draft_slots:
            if slot.day == day:
                used.append(slot.room)
        return used


    def get_used_lecturers_on_day(self, day):
        """
        Returns a list of lecturer names already assigned on the given day.
        Used by get_available_day() and get_free_lecturers_on_day() internally,
        and by the check_lecturer tool via agent deps.
        """
        used = []
        for slot in self.draft_slots:
            if slot.day == day:
                used.append(slot.lecturer)
        return used


    def get_free_rooms_on_day(self, day):
        """
        Returns full Room objects that are not yet assigned on the given day.
        Returns full objects — not just names — because agents need
        room.is_lab to reason about suitability for lab vs regular courses.
        Called by the orchestrator before each room_agent call.
        """
        used_names = self.get_used_rooms_on_day(day)
        free = []
        for room in self.rooms:
            if room.name not in used_names:
                free.append(room)
        return free


    def get_free_lecturers_on_day(self, day):
        """
        Returns full Lecturer objects that are not yet assigned on the given day.
        Returns full objects — not just names — because agents need
        lecturer.subjects to reason about qualification for a course.
        Called by the orchestrator before each lecturer_agent call.
        """
        used_names = self.get_used_lecturers_on_day(day)
        free = []
        for lecturer in self.lecturers:
            if lecturer.name not in used_names:
                free.append(lecturer)
        return free


    # --- write operations ---
    # only the orchestrator calls these

    def write_slot(self, slot):
        """
        Appends a completed TimetableSlot to draft_slots.
        Called by the orchestrator only after both agents return success.
        The reflexion check runs immediately after this call.
        """
        self.draft_slots.append(slot)


    def remove_last_slot(self):
        """
        Removes the most recently written slot from draft_slots.
        Called by the orchestrator when the reflexion check detects
        a conflict after a write — restores the board to its pre-write state.
        """
        if len(self.draft_slots) > 0:
            self.draft_slots.pop()


    # --- conflict and failure logging ---

    def log_conflict(self, message):
        """
        Records a conflict message detected during the reflexion check.
        The orchestrator reads has_conflicts() after check_conflicts()
        to decide whether to undo the last write.
        """
        self.conflicts.append(message)


    def clear_conflicts(self):
        """
        Clears all conflict messages before each reflexion check.
        Must be called at the start of every check_conflicts() call —
        without this, resolved conflicts from previous iterations
        would persist and has_conflicts() would never return False.
        """
        self.conflicts = []


    def log_failure(self, failure):
        """
        Records a SchedulingFailure when an agent returns success=False
        or when no valid day is available for a course.
        Failures accumulate for the entire run and are reported
        in main.py if the timetable cannot be completed.
        """
        self.failures.append(failure)


    # --- goal and state checks ---

    def is_complete(self):
        """
        The goal condition for the orchestrator control loop.
        Returns True when all courses have been successfully scheduled —
        meaning the unscheduled list is empty.
        This is what makes the orchestrator goal-oriented, not pipeline-oriented.
        """
        return len(self.unscheduled) == 0


    def has_conflicts(self):
        """
        Returns True if the last reflexion check found any clashes.
        Read by the orchestrator immediately after check_conflicts()
        to decide whether to undo the last slot write.
        """
        return len(self.conflicts) > 0


    def get_final_timetable(self):
        """
        Returns the completed list of TimetableSlots.
        Called by the orchestrator after is_complete() returns True.
        Returns a copy — not the internal list — to prevent
        accidental modification after the run is finished.
        """
        return list(self.draft_slots)