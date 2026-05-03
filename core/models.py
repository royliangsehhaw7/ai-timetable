from pydantic import BaseModel


# --- source entities ---

class Course(BaseModel):
    name: str
    requires_lab: bool


class Room(BaseModel):
    name: str
    is_lab: bool


class Lecturer(BaseModel):
    name: str
    subjects: list[str]


class Policy(BaseModel):
    school_days: list[str]
    school_start_hour: int
    school_end_hour: int
    lunch_start_hour: int
    lunch_end_hour: int


# --- output model ---

class TimetableSlot(BaseModel):
    day: str
    course: str
    room: str
    lecturer: str


# --- agent result models ---

class RoomSuggestion(BaseModel):
    success: bool
    room: str | None
    day: str | None
    reason: str


class LecturerSuggestion(BaseModel):
    success: bool
    lecturer: str | None
    day: str | None
    reason: str


# --- failure tracking ---

class SchedulingFailure(BaseModel):
    course: str
    agent: str
    day: str
    reason: str