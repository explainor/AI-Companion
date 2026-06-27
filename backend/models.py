from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Persona(SQLModel, table=True):
    __tablename__ = "personas"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    system_prompt: str
    is_system: int = 0
    model_role: str = Field(default="chat_strong", index=True)
    model_override: Optional[str] = None
    sim_config: Optional[str] = None


class Channel(SQLModel, table=True):
    __tablename__ = "channels"

    id: Optional[int] = Field(default=None, primary_key=True)
    type: str
    title: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    is_system: int = 0
    pinned: Optional[int] = None
    archived: Optional[int] = None
    ai_enabled: bool = True


class ChannelMember(SQLModel, table=True):
    __tablename__ = "channel_members"

    id: Optional[int] = Field(default=None, primary_key=True)
    channel_id: int = Field(foreign_key="channels.id", index=True)
    member_type: str = Field(default="persona", index=True)
    persona_id: Optional[int] = Field(default=None, foreign_key="personas.id", index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    display_name: str = Field(index=True)
    created_at: str = Field(default_factory=now_iso)


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    channel_id: int = Field(foreign_key="channels.id", index=True)
    sender: str
    persona_id: Optional[int] = Field(default=None, foreign_key="personas.id")
    author_type: str = Field(default="human", index=True)
    author_user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    ai_enabled_snapshot: bool = True
    content: str
    created_at: str = Field(default_factory=now_iso, index=True)
    status: Optional[str] = "delivered"
    chunk_group: Optional[str] = None


class InterjectionDecision(SQLModel, table=True):
    __tablename__ = "interjection_decisions"

    id: Optional[int] = Field(default=None, primary_key=True)
    channel_id: int = Field(foreign_key="channels.id", index=True)
    created_at: str = Field(default_factory=now_iso, index=True)
    considered: bool = False
    spoke: bool = False
    trigger_reason: str = ""
    suppressed_reason: Optional[str] = None
    latency_ms: Optional[int] = None


class PersonaNote(SQLModel, table=True):
    __tablename__ = "persona_notes"

    id: Optional[int] = Field(default=None, primary_key=True)
    persona_id: int = Field(foreign_key="personas.id", index=True)
    content: str
    updated_at: str = Field(default_factory=now_iso)


class PersonaCard(SQLModel, table=True):
    __tablename__ = "persona_card"

    persona_id: int = Field(foreign_key="personas.id", primary_key=True)
    persona_core: str = ""
    speaking_style: str = ""
    example_dialogues: str = "[]"
    world_info: Optional[str] = None
    voice: Optional[str] = None
    traits: str = "[]"


class Todo(SQLModel, table=True):
    __tablename__ = "todos"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    status: str = Field(default="pending", index=True)
    due_time: Optional[str] = None
    priority: str = "med"
    notes: Optional[str] = None
    repeat_rule: Optional[str] = None
    source: str = "steward"
    result: Optional[str] = None
    source_channel: Optional[int] = Field(default=None, foreign_key="channels.id")
    created_at: str = Field(default_factory=now_iso)
    completed_at: Optional[str] = None


class Memo(SQLModel, table=True):
    __tablename__ = "memos"

    id: Optional[int] = Field(default=None, primary_key=True)
    content: str
    created_at: str = Field(default_factory=now_iso)


class Setting(SQLModel, table=True):
    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: str


class PersonaState(SQLModel, table=True):
    __tablename__ = "persona_state"

    persona_id: int = Field(foreign_key="personas.id", primary_key=True)
    familiarity: float = 0.0
    last_tone: Optional[str] = None
    last_interaction: Optional[str] = None
    last_interaction_at: Optional[str] = None
    milestones: Optional[str] = "[]"


class Habit(SQLModel, table=True):
    __tablename__ = "habits"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    schedule: str
    created_at: str = Field(default_factory=now_iso)


class HabitLog(SQLModel, table=True):
    __tablename__ = "habit_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    habit_id: int = Field(foreign_key="habits.id", index=True)
    value: Optional[float] = None
    ts: str = Field(default_factory=now_iso, index=True)
