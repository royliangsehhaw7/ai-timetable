# SPECIFICATIONS — Weekly Timetable Generator

---

## 0. Instructions for Coding Agents

This section is for any coding agent (aider, Claude, etc.) reading this file at the start of a new session. Read this section first and follow it for the entire session.

### 0.1 What This Project Is

A pydantic-ai multi-agent timetable generator. Full details in §1 onwards. The developer works one file at a time, reads and understands each file, then copies it manually. Do not generate multiple files at once.

### 0.2 How to Find the Current Task

The developer will attach `PROGRESS.md` alongside this file. Read `PROGRESS.md` to find the first unchecked task `[ ]`. That is the only task for this session. Do not work ahead.

### 0.3 Coding Rules — Non-Negotiable

These apply to every file in this project without exception:

| Rule | Detail |
|------|--------|
| **Imperative style only** | Use explicit loops and named variables. No lambdas, no chained comprehensions, no functional abstractions |
| **One file, one job** | Every file has exactly one responsibility as defined in §6.2. Do not add anything outside that definition |
| **No agent-to-agent imports** | Agents are unaware of each other. Only the orchestrator imports agents |
| **Agent result contract** | Every agent result must carry `success: bool`, `reason: str`, and a nullable value field. See §8.3 |
| **Orchestrator is the only writer** | Tools and agents never write to the Blackboard. Only the orchestrator does |
| **Orchestrator is plain Python** | The orchestrator is a plain Python class — not a pydantic-ai `Agent`. It runs a deterministic control loop. No LLM is involved in orchestration decisions. Only the room and lecturer agents use LLMs |
| **Plain names** | No jargon names like `temporal`, `spatial`, `stratified`, `handler`, `manager`, `processor` |
| **Log everything** | Every orchestrator decision, agent call, and conflict must be logged via `core/log.py` |

### 0.4 Before Writing Any Code

1. Read the SRP table in §6.2 and find the row for the file being requested
2. Read the section that describes that file's behaviour in detail
3. Write only what is in scope for that file — nothing more

### 0.5 After Writing the Code

State clearly:
- What the file does in one sentence
- What other files it imports from
- What files will import from it later
- Any assumption made that is not covered by the spec

---

## 1. Project Description

A multi-agent system built with **pydantic-ai** that generates a weekly class timetable (Monday–Friday) from four source entities: **Courses**, **Rooms**, **Lecturers**, and **Policies**. The system assigns each course a day, room, and lecturer — without any clashes — while respecting the school's scheduling policies.

The timetable output is flat and simple:

| Day       | Course      | Room   | Lecturer   |
|-----------|-------------|--------|------------|
| Monday    | Mathematics | Lab A  | Dr. Siti   |
| Tuesday   | Physics     | Room 3 | Mr. Haziq  |
| ...       | ...         | ...    | ...        |

No dates are involved. The schedule repeats every week.

---

## 2. Purpose

- Demonstrate a **real orchestrator-based multi-agent architecture** using pydantic-ai — not a simple sequential pipeline.
- Practice the **Blackboard, Mediator, and Reflexion** design patterns within a star topology.
- Keep all logic explicit, readable, and imperative — no hidden functional abstractions.
- Produce a clean, conflict-free timetable that respects policy constraints.

---

## 3. Source Entities

These are the raw data models the system works with. Each entity carries just enough context for agents to make meaningful judgments — not just availability checks.

### 3.1 Course
```python
class Course(BaseModel):
    name: str                # e.g. "Chemistry Practical"
    requires_lab: bool       # True = needs a lab room, False = regular room is fine
```

### 3.2 Room
```python
class Room(BaseModel):
    name: str                # e.g. "Lab A"
    is_lab: bool             # True = lab room, False = regular classroom
```

### 3.3 Lecturer
```python
class Lecturer(BaseModel):
    name: str                # e.g. "Dr. Siti"
    subjects: list[str]      # e.g. ["Mathematics", "Physics"]
```

### 3.4 Policy
```python
class Policy(BaseModel):
    school_days: list[str]   # e.g. ["Tuesday", "Wednesday", "Thursday", "Friday"]
    school_start_hour: int   # e.g. 8  (08:00)
    school_end_hour: int     # e.g. 17 (17:00)
    lunch_start_hour: int    # e.g. 12 (12:00)
    lunch_end_hour: int      # e.g. 13 (13:00)
```

Policies act as hard constraints. The orchestrator must never assume which days are valid — it always reads `policy.school_days` from the Blackboard. Any slot that falls during lunch or outside school hours is also invalid.

---

## 4. Output Model

```python
class TimetableSlot(BaseModel):
    day: str           # "Monday" | "Tuesday" | ... | "Friday"
    course: str        # Course name
    room: str          # Room name
    lecturer: str      # Lecturer name
```

A complete timetable is a list of `TimetableSlot` — one per course.

---

## 5. Design Patterns

### 5.1 Blackboard Pattern
A shared in-memory state object (`Blackboard`) holds the current state of the timetable being built. Only the orchestrator reads from and writes to the Blackboard. Agents never touch it directly.

```
Blackboard
├── courses: list[Course]
├── rooms: list[Room]
├── lecturers: list[Lecturer]
├── policy: Policy
├── draft_slots: list[TimetableSlot]       # work in progress
├── conflicts: list[str]                   # detected clashes
└── failures: list[SchedulingFailure]      # agent-reported dead ends
```

Key methods the orchestrator uses to query the Blackboard — never assumed, always asked:

| Method | Returns | Purpose |
|--------|---------|---------|
| `get_next_unscheduled_course()` | `Course \| None` | Next course with no slot yet |
| `get_available_day()` | `str \| None` | First valid school day that still has at least one free room AND one free lecturer. Returns `None` if no day qualifies |
| `get_used_rooms_on_day(day)` | `list[str]` | Room names already assigned on that day |
| `get_used_lecturers_on_day(day)` | `list[str]` | Lecturer names already assigned on that day |
| `is_complete()` | `bool` | True when every course has a slot |
| `has_conflicts()` | `bool` | True if conflicts list is non-empty after last check |

`get_available_day()` checks against `policy.school_days` — it will never return a day not listed in the policy. This is the single place where policy-day validation lives.

### 5.2 Mediator Pattern (Orchestrator)
The **Orchestrator** is the sole mediator. It is the only component that:
- Calls agents
- Reads results from agents
- Writes updates back to the Blackboard

Agents do **not** talk to each other. All inter-agent coordination goes through the Orchestrator. This is a strict **star topology**.

```
           ┌─────────────┐
           │ Orchestrator │
           └──────┬───────┘
        ┌─────────┼─────────┐
        ▼         ▼         ▼
   RoomAgent  LecturerAgent  (future agents)
```

### 5.3 Reflexion Pattern
After each round of agent calls, the Orchestrator evaluates the Blackboard for:
- Room double-bookings on the same day
- Lecturer double-bookings on the same day
- Slots that violate policy (outside hours, during lunch)

If conflicts are found, the Orchestrator triggers a **revision cycle** — it instructs the relevant agent to retry with updated constraints. This loop continues until the timetable is conflict-free or a retry limit is reached.

```
Orchestrator
  → call agents
  → evaluate blackboard
  → conflicts found? → revise → repeat
  → no conflicts? → finalise timetable
```

---

## 6. Architecture

### 6.1 Folder Structure

```
project/
│
├── core/
│   ├── deps.py              # pydantic-ai dependency container (wraps Blackboard)
│   ├── models.py            # All pydantic models: entities, results, failures, timetable slot
│   ├── log.py               # Logging setup — one logger, used everywhere
│   └── llm_factory.py       # Builds and returns the configured LLM model for agents
│
├── database/
│   ├── courses.json         # Raw course data   [{"name": "Chemistry Practical", "requires_lab": true}, ...]
│   ├── rooms.json           # Raw room data     [{"name": "Lab A", "is_lab": true}, ...]
│   ├── lecturers.json       # Raw lecturer data [{"name": "Dr. Siti", "subjects": ["Mathematics"]}, ...]
│   └── policy.json          # School policy     {"school_days": ["Tuesday", ...], "school_start_hour": 8, ...}
│
├── tools/
│   ├── get_courses.py       # Reads courses.json    → returns list[Course]
│   ├── get_rooms.py         # Reads rooms.json      → returns list[Room]
│   ├── get_lecturers.py     # Reads lecturers.json  → returns list[Lecturer]
│   ├── get_policy.py        # Reads policy.json     → returns Policy
│   ├── check_room.py        # Is this room free on this day?     → bool + reason
│   └── check_lecturer.py    # Is this lecturer free on this day? → bool + reason
│
├── agents/
│   ├── room_agent.py        # Suggests a room for a course+day → RoomSuggestion
│   └── lecturer_agent.py    # Suggests a lecturer for a course+day → LecturerSuggestion
│
├── orchestrator/
│   └── orchestrator.py      # Control loop: drives scheduling, mediates agents, applies reflexion
│
├── blackboard/
│   └── board.py             # Blackboard class: owns all shared mutable state
│
└── main.py                  # Entry point: load data, run orchestrator, print timetable
```

### 6.2 SRP Mapping

| File | Single Responsibility |
|------|-----------------------|
| `core/models.py` | Define all data shapes — entities, result types, `SchedulingFailure`, `TimetableSlot` |
| `core/deps.py` | Define `AgentDeps` — a single dataclass with one field `board: Blackboard`. Imported by both agents so they share a common deps type without importing from each other |
| `core/log.py` | Configure and expose the logger |
| `core/llm_factory.py` | Read `LLM_PROVIDER` from environment, build and return the configured LLM model. Called by agents at definition time. Switching providers requires only a `.env` change — no code changes |
| `database/courses.json` | Source of truth for course data |
| `database/rooms.json` | Source of truth for room data |
| `database/lecturers.json` | Source of truth for lecturer data |
| `database/policy.json` | Source of truth for policy data |
| `blackboard/board.py` | Own and mutate all shared scheduling state. Expose query methods including `get_available_day()` which enforces policy.school_days |
| `tools/get_courses.py` | Read `courses.json` and return `list[Course]` — nothing else |
| `tools/get_rooms.py` | Read `rooms.json` and return `list[Room]` — nothing else |
| `tools/get_lecturers.py` | Read `lecturers.json` and return `list[Lecturer]` — nothing else |
| `tools/get_policy.py` | Read `policy.json` and return `Policy` — nothing else |
| `tools/check_room.py` | Answer "is this room free on this day?" — reads Blackboard state only |
| `tools/check_lecturer.py` | Answer "is this lecturer free on this day?" — reads Blackboard state only |
| `agents/room_agent.py` | Propose a room assignment — always returns `RoomSuggestion` |
| `agents/lecturer_agent.py` | Propose a lecturer assignment — always returns `LecturerSuggestion` |
| `orchestrator/orchestrator.py` | Drive the control loop, mediate agents, apply reflexion, handle failures |
| `main.py` | Wire everything together and run |

> **Refactoring note:** When the prototype is stable, the four `get_*.py` tools are the only files that need to change to switch from JSON to a real database. Everything else — agents, orchestrator, Blackboard — remains untouched. This is SRP paying off.

---

## 7. Orchestrator Behaviour (Non-Pipeline)

### 7.1 Why This Is Not a Pipeline

A pipeline has a fixed order: step 1 → step 2 → step 3 → done. Each step runs once. There is no decision-making between steps — just hand-off.

The orchestrator here is a **control loop**. After every agent call and every Blackboard write, the orchestrator stops and asks: *"What does the Blackboard tell me right now? Is it valid? What needs to happen next?"* It can loop back, skip forward, defer a course, or retry with different constraints. The order of work is decided at runtime by reading state — not hardcoded in the program.

The simplest way to spot a disguised pipeline: if removing the `while` loop and flattening the code into a straight call sequence still produces the same result, it was a pipeline all along.

### 7.2 The Mental Model

Think of the orchestrator as a **foreman on a building site**. The room agent and lecturer agent are specialist workers. The foreman does not say "first you build the wall, then you wire the electrics, done." The foreman:

- Looks at what is built so far (Blackboard)
- Decides what the next problem to solve is
- Sends the right worker to tackle that specific problem
- Checks the worker's result before accepting it
- Decides if it is acceptable or needs to be redone
- Loops until the building is complete — or declares it cannot be finished

The workers never talk to each other. They only report back to the foreman.

### 7.3 The Control Loop (Pseudocode)

```
load all data onto Blackboard

retry_count = 0

LOOP while Blackboard has unscheduled courses:

    if retry_count > MAX_RETRIES:
        raise SchedulingError — cannot resolve

    course = Blackboard.get_next_unscheduled_course()

    --- ask Blackboard for a valid day ---
    day = Blackboard.get_available_day()
    # checks: day is in policy.school_days
    #         at least one room is free on that day
    #         at least one lecturer is free on that day

    if day is None:
        log failure — no valid day available for this course
        defer course
        retry_count += 1
        CONTINUE to top of loop          ← do not proceed without a valid day

    --- call RoomAgent ---
    room_result = RoomAgent.run(course, day)

    if room_result.success is False:
        log failure to Blackboard
        defer course
        retry_count += 1
        CONTINUE to top of loop          ← do not proceed blindly

    --- call LecturerAgent ---
    lecturer_result = LecturerAgent.run(course, day)

    if lecturer_result.success is False:
        log failure to Blackboard
        defer course
        retry_count += 1
        CONTINUE to top of loop          ← stop, loop back

    --- write to Blackboard ---
    write slot (course, day, room, lecturer) to Blackboard

    --- Reflexion check ---
    run conflict check on entire Blackboard

    if conflicts found:
        remove the slot just written
        log conflict to Blackboard
        defer course
        retry_count += 1
        CONTINUE to top of loop          ← self-correct, never accept bad state

END LOOP

return final timetable from Blackboard
```

The `CONTINUE` statements are what make this a real orchestrator loop — every failure, every conflict, sends control back to the top where the orchestrator reassesses state before deciding what to do next. The orchestrator never assumes a day is valid — it always asks the Blackboard.

### 7.4 The Three Patterns in the Loop

| Pattern | Where it appears in the loop |
|---------|------------------------------|
| **Blackboard** | Every read (`pick next course`, `pick day`, `conflict check`) and every write (`write slot`, `log failure`) goes through the Blackboard |
| **Mediator** | The orchestrator is the only caller of agents — agents never appear in each other's code |
| **Reflexion** | The conflict check after every Blackboard write — the orchestrator inspects its own work and corrects it before moving on |

These are not three separate phases. They are three roles the orchestrator plays inside the same loop, on every iteration.

---

## 8. Agent Contracts

Each agent is a pydantic-ai `Agent` with typed deps and a typed result. Every agent **always** returns a structured result — success or failure. The orchestrator always checks `result.success` before doing anything with the result. Agents never raise exceptions for unavailability; they return a failure result instead.

### 8.0 AgentDeps (core/deps.py)

`AgentDeps` is the dependency container passed into every agent at runtime by the orchestrator. It gives agents read access to the Blackboard so their tools can query current availability without writing to it.

**The file contains exactly this — nothing more:**

```python
from dataclasses import dataclass
from blackboard.board import Blackboard

@dataclass
class AgentDeps:
    board: Blackboard
```

**How it connects to a pydantic-ai agent:**

Each agent declares `AgentDeps` as its deps type when it is defined:

```python
from pydantic_ai import Agent
from core.deps import AgentDeps
from core.models import RoomSuggestion

room_agent = Agent(
    model="...",
    deps_type=AgentDeps,
    result_type=RoomSuggestion,
)
```

When the orchestrator calls an agent, it constructs and passes an `AgentDeps` instance:

```python
deps = AgentDeps(board=self.board)
result = await room_agent.run(prompt, deps=deps)
```

Inside a tool registered to the agent, `AgentDeps` is accessed via the `RunContext`:

```python
from pydantic_ai import RunContext
from core.deps import AgentDeps

async def check_room(ctx: RunContext[AgentDeps], room_name: str, day: str) -> str:
    used_rooms = ctx.deps.board.get_used_rooms_on_day(day)
    # ... check and return result
```

**Rules for `AgentDeps`:**

| Rule | Detail |
|------|--------|
| Defined once | Only in `core/deps.py` — never inside an agent file |
| Shared import | Both `room_agent.py` and `lecturer_agent.py` import from `core/deps.py` — never from each other |
| Read-only access | Agents call Blackboard query methods only — never write methods |
| Orchestrator constructs it | The orchestrator builds `AgentDeps(board=self.board)` before every agent call |
| Tools access it via context | Tools receive deps through `RunContext[AgentDeps]` — never as a direct argument |

### 8.1 RoomAgent

- **Input (via deps):** Blackboard — read-only access to get free rooms on a given day
- **Task:** Given a course and target day, find a free room that is **suitable for the course** — meaning if `course.requires_lab` is True, the room must also have `is_lab=True`. This is a genuine reasoning task, not just a list check.
- **Tools available:** `check_room`
- **What the LLM reasons about:** Which of the available free rooms on this day actually fits what this course needs
- **Output:**

```python
class RoomSuggestion(BaseModel):
    success: bool
    room: str | None      # populated only when success is True
    day: str | None       # populated only when success is True
    reason: str           # always populated — e.g. "Lab A assigned: Chemistry requires a lab"
                          #                         "No lab rooms free on Tuesday"
```

### 8.2 LecturerAgent

- **Input (via deps):** Blackboard — read-only access to get free lecturers on a given day
- **Task:** Given a course and target day, find a free lecturer who **teaches this subject** — meaning the lecturer's `subjects` list must include the course name. This is a genuine reasoning task, not just a list check.
- **Tools available:** `check_lecturer`
- **What the LLM reasons about:** Which of the available free lecturers on this day is actually qualified to teach this course
- **Output:**

```python
class LecturerSuggestion(BaseModel):
    success: bool
    lecturer: str | None  # populated only when success is True
    day: str | None       # populated only when success is True
    reason: str           # always populated — e.g. "Dr. Siti assigned: teaches Mathematics"
                          #                         "No qualified lecturers free on Wednesday"
```

### 8.3 Agent Result Contract (Shared Rules)

These rules apply to every agent in the system:

| Rule | Detail |
|------|--------|
| Always return a result | Agents never raise exceptions for unavailability — they return `success=False` |
| Always populate `reason` | Even on success, `reason` must be filled — it goes into the log |
| Never write to Blackboard | Agents only return results; the orchestrator decides what to write |
| Never call another agent | Agents are unaware of each other's existence |
| `None` fields on failure | `room`, `day`, `lecturer` are `None` when `success=False` — orchestrator must not read them |

### 8.4 SchedulingFailure (Blackboard Record)

When an agent returns `success=False`, the orchestrator writes a `SchedulingFailure` to the Blackboard before looping back:

```python
class SchedulingFailure(BaseModel):
    course: str       # which course could not be scheduled
    agent: str        # which agent reported the failure: "room_agent" | "lecturer_agent"
    day: str          # which day was attempted
    reason: str       # copied from agent result
```

This record is used at the end of the run to produce a clear error report if the timetable could not be completed.

---

## 9. Conflict Rules

A timetable slot is **invalid** if any of the following are true:

| Rule | Description |
|------|-------------|
| Room clash | Same room assigned to two courses on the same day |
| Lecturer clash | Same lecturer assigned to two courses on the same day |
| Outside hours | Slot assigned outside `school_start_hour` – `school_end_hour` |
| Lunch conflict | Slot falls within `lunch_start_hour` – `lunch_end_hour` |

The orchestrator checks all rules after each agent round. Agents are only told about violations that affect their domain (room agent gets room conflicts, lecturer agent gets lecturer conflicts).

---

## 10. Constraints & Assumptions

- Valid school days are defined in `policy.school_days` — never hardcoded anywhere else in the system. Monday through Friday are possible days but which ones are active is determined solely by the policy
- One course per slot; each course appears exactly once in the final timetable
- Rooms and lecturers are reusable across days but not within the same day
- Policy is a single global object — all courses share the same policy
- **All hours are whole integers only — no minutes, no half-hours.** e.g. `8` means 08:00, `17` means 17:00. No time formatting, no datetime objects, no string parsing
- Data is loaded from Python dicts/lists for now (no database)
- Max retry limit for reflexion: **5 rounds** before raising an error
- No partial or overlapping time slots — slots are day-level only (no hours per slot except policy bounds)
- **Keep data simple and logic straightforward** — the goal of this project is to learn multi-agent orchestration design, not to build a sophisticated scheduling algorithm

---

## 11. Non-Functional Requirements

| Concern | Requirement |
|---------|-------------|
| Code style | Imperative — explicit loops, clear variable names, no lambdas or comprehension chains |
| Naming | Plain English names — no domain jargon like "temporal", "spatial", "stratified" |
| Logging | Log every orchestrator decision, every agent call, every conflict found |
| Separation | Each file has one job; no file imports from a file that is not its declared dependency |
| Agent comms | Agents never call each other; only the orchestrator calls agents |
| Testability | Each tool function is a plain Python function — testable without running an agent |

---

## 12. Out of Scope (v1)

- Time slots within a day (all slots are day-level)
- Student group assignments
- Room capacity limits
- Lecturer preferences or availability windows
- Persistent storage (database, file)
- Web UI or REST API
- Async execution

---

## 13. Glossary

| Term | Meaning |
|------|---------|
| Blackboard | Shared mutable state object read/written only by the orchestrator |
| Slot | One row in the timetable: day + course + room + lecturer |
| Clash | Two slots sharing the same room or lecturer on the same day |
| Reflexion | The orchestrator's self-correction loop — checking and fixing state after every write |
| Orchestrator | A plain Python class — the central controller. Not a pydantic-ai Agent. The only component that calls agents |
| Star topology | All communication routes through the orchestrator; no agent-to-agent calls |
| SchedulingFailure | A structured record written to the Blackboard when an agent cannot find a valid assignment |
| Agent Result Contract | The rule that every agent always returns a typed success/failure result — never raises for unavailability |
| `get_available_day()` | Blackboard method that returns the first valid school day with at least one free room and one free lecturer — never returns a day outside `policy.school_days` |

---

*End of SPECIFICATIONS.md*