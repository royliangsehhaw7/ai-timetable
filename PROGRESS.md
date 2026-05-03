# PROGRESS — Weekly Timetable Generator

Tick each task `[x]` when the code is written, copied in, and manually verified to work before moving to the next.

---

## Phase 1 — Foundation

- [ ] **1.1** Create project folder structure (all empty files and folders as per SPECIFICATIONS §6.1)
- [ ] **1.2** Create `database/courses.json` — add at least 5 sample courses, each with `name` and `requires_lab` (true/false)
- [ ] **1.3** Create `database/rooms.json` — add at least 3 sample rooms, each with `name` and `is_lab` (true/false). Include at least one lab and one regular room
- [ ] **1.4** Create `database/lecturers.json` — add at least 3 sample lecturers, each with `name` and `subjects` (list of course names they can teach)
- [ ] **1.5** Create `database/policy.json` — set `school_days` (e.g. Tuesday–Friday), school hours and lunch hours

---

## Phase 2 — Core Models

- [ ] **2.1** Write `core/log.py` — logger setup, verify it prints to console
- [ ] **2.2** Write `core/llm_factory.py` — `LLMModelFactory` class with:
  - `__init__(self, provider: str)` — reads provider name only, no api key as argument
  - `get_model()` — reads api key from `os.environ`, returns configured model
  - Supports `"gemini"` → `GoogleModel` with `GEMINI_API_KEY`
  - Supports `"openrouter"` → `OpenAIChatModel` with `OPENROUTER_API_KEY`
  - Raises `ValueError` for unknown provider
  - `LLM_PROVIDER` env var drives which provider is used — no code change needed to switch
- [ ] **2.3** Write `core/models.py` — all pydantic models in this order:
  - `Course` (name, requires_lab), `Room` (name, is_lab), `Lecturer` (name, subjects), `Policy`
  - `TimetableSlot`
  - `RoomSuggestion`, `LecturerSuggestion`
  - `SchedulingFailure`
- [ ] **2.4** Write `core/deps.py` — a single dataclass `AgentDeps` with one field: `board: Blackboard`
  - Import `Blackboard` from `blackboard/board.py`
  - This file exists so both agents import deps from `core/` and never from each other
  - Nothing else goes in this file

---

## Phase 3 — Blackboard

- [ ] **3.1** Write `blackboard/board.py` — the `Blackboard` class with these fields and methods:
  - Fields: `courses`, `rooms`, `lecturers`, `policy`, `draft_slots`, `conflicts`, `failures`
  - `get_next_unscheduled_course()` — returns next course not yet in draft_slots
  - `get_available_day()` — returns first day in `policy.school_days` that still has a free room AND a free lecturer. Returns `None` if no day qualifies
  - `get_used_rooms_on_day(day)` — returns list of room names already assigned on that day
  - `get_used_lecturers_on_day(day)` — returns list of lecturer names already assigned on that day
  - `write_slot(slot)` — appends a TimetableSlot to draft_slots
  - `remove_last_slot()` — pops the last written slot (used during reflexion)
  - `log_conflict(message)` — appends to conflicts list
  - `log_failure(failure)` — appends a SchedulingFailure to failures list
  - `defer_course(course)` — puts course back into the unscheduled pool
  - `is_complete()` — returns True when all courses have a slot
  - `has_conflicts()` — returns True if conflicts list is non-empty after last check
- [ ] **3.2** Manually test `board.py` in a scratch script — write a slot, remove it, check state

---

## Phase 4 — Tools

- [ ] **4.1** Write `tools/get_data.py` — one function per entity:
  - `get_courses()` — reads `database/courses.json`, returns `list[Course]`
  - `get_rooms()` — reads `database/rooms.json`, returns `list[Room]`
  - `get_lecturers()` — reads `database/lecturers.json`, returns `list[Lecturer]`
  - `get_policy()` — reads `database/policy.json`, returns `Policy`
- [ ] **4.2** Manually test `get_data.py` — call each function and print the result
- [ ] **4.3** Write `tools/check_room.py` — function `check_room(room_name, day, board)`:
  - Returns `(True, "Room X is free on Monday")` if not in `board.get_used_rooms_on_day(day)`
  - Returns `(False, "Room X is already taken on Monday")` if taken
- [ ] **4.4** Write `tools/check_lecturer.py` — function `check_lecturer(lecturer_name, day, board)`:
  - Returns `(True, "Dr. X is free on Monday")` if not in `board.get_used_lecturers_on_day(day)`
  - Returns `(False, "Dr. X is already assigned on Monday")` if taken
- [ ] **4.5** Manually test both check tools with a populated Blackboard — confirm True/False cases

---

## Phase 5 — Agents

- [ ] **5.1** Write `agents/room_agent.py` — pydantic-ai Agent that:
  - Receives course name, `requires_lab` flag, and day via prompt
  - Uses `check_room` tool to get free rooms on that day
  - Reasons about which free room suits the course — lab room for lab courses, regular room otherwise
  - Returns `RoomSuggestion` with `success`, `room`, `day`, `reason`
- [ ] **5.2** Run `room_agent` standalone — verify it correctly assigns a lab room to a lab course
- [ ] **5.3** Run `room_agent` with no suitable room free — verify it returns `success=False` with a clear reason
- [ ] **5.4** Write `agents/lecturer_agent.py` — pydantic-ai Agent that:
  - Receives course name and day via prompt
  - Uses `check_lecturer` tool to get free lecturers on that day
  - Reasons about which free lecturer teaches this subject — checks `lecturer.subjects` against course name
  - Returns `LecturerSuggestion` with `success`, `lecturer`, `day`, `reason`
- [ ] **5.5** Run `lecturer_agent` standalone — verify it correctly assigns a qualified lecturer
- [ ] **5.6** Run `lecturer_agent` with no qualified lecturer free — verify it returns `success=False` with a clear reason

---

## Phase 6 — Orchestrator

- [ ] **6.1** Write `orchestrator/orchestrator.py` — the `Orchestrator` class with:
  - `__init__` — receives `room_agent`, `lecturer_agent`, initialises Blackboard
  - `load_data()` — calls all four `get_data` functions, writes to Blackboard
  - `check_conflicts()` — inspects draft_slots for room and lecturer clashes, writes to `board.conflicts`
  - `run()` — the main control loop (see SPECIFICATIONS §7.3)
- [ ] **6.2** Trace through the `run()` loop manually on paper before testing:
  - Pick one course, simulate a successful room + lecturer assignment
  - Pick a second course on the same day, simulate a room clash
  - Confirm the loop defers and retries — not skips
- [ ] **6.3** Run the orchestrator with the full sample data — verify a complete timetable is returned
- [ ] **6.4** Introduce a forced conflict (two courses, one room, one day) — verify the reflexion loop resolves it
- [ ] **6.5** Introduce an impossible case (more courses than rooms × days) — verify a clean `SchedulingError` is raised with a failure report

---

## Phase 7 — Entry Point

- [ ] **7.1** Write `main.py` — wire together and run:
  - Instantiate agents
  - Instantiate orchestrator with agents
  - Call `orchestrator.run()`
  - Print final timetable as a readable table
  - Print any failures if scheduling was incomplete
- [ ] **7.2** Run `main.py` end-to-end with sample data — verify clean output
- [ ] **7.3** Check logs — confirm every orchestrator decision, agent call, and conflict is logged

---

## Phase 8 — Review

- [ ] **8.1** Re-read each file against SPECIFICATIONS — confirm no file has more than one responsibility
- [ ] **8.2** Confirm no agent imports from another agent
- [ ] **8.3** Confirm no tool writes to the Blackboard (read only)
- [ ] **8.4** Confirm the orchestrator is the only caller of agents
- [ ] **8.5** Confirm all agent results carry `success`, `reason`, and nullable value fields
- [ ] **8.6** Write a short `NOTES.md` in your own words — one paragraph per file explaining what it does and why

---

*End of PROGRESS.md*