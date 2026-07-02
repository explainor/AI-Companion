from typing import Optional

from pydantic import BaseModel


class ChannelCreate(BaseModel):
    type: str
    title: Optional[str] = None
    persona_ids: list[int]
    user_ids: list[int] = []


class ChannelUpdate(BaseModel):
    title: Optional[str] = None
    pinned: Optional[int] = None
    archived: Optional[int] = None


class MessageCreate(BaseModel):
    content: Optional[str] = None
    text: Optional[str] = None
    type: str = "text"
    mentions: list[str] = []
    mentioned_member_ids: list[int] = []
    media_url: Optional[str] = None
    mime_type: Optional[str] = None
    file_name: Optional[str] = None


class ChannelRead(BaseModel):
    id: int
    type: str
    title: Optional[str]
    created_at: str
    is_system: int = 0
    pinned: Optional[int] = None
    archived: Optional[int] = None
    ai_enabled: bool = True
    created_by_user_id: Optional[int] = None
    members: list[dict]


class MessageRead(BaseModel):
    id: int
    channel_id: int
    sender: str
    persona_id: Optional[int]
    persona_name: Optional[str] = None
    author_type: str = "human"
    author_user_id: Optional[int] = None
    author_user_name: Optional[str] = None
    author_avatar_url: Optional[str] = None
    ai_enabled_snapshot: bool = True
    type: str = "text"
    media_url: Optional[str] = None
    mime_type: Optional[str] = None
    file_name: Optional[str] = None
    content: str
    created_at: str
    status: Optional[str] = None
    chunk_group: Optional[str] = None


class SettingUpdate(BaseModel):
    value: str


class PersonaModelUpdate(BaseModel):
    model_role: Optional[str] = None
    model_override: Optional[str] = None
    sim_config: Optional[str] = None


class PersonaCardUpdate(BaseModel):
    owner_user_id: Optional[int] = None
    persona_core: Optional[str] = None
    self_identity: Optional[str] = None
    relationship_backstory: Optional[str] = None
    speaking_style: Optional[str] = None
    example_dialogues: Optional[str] = None
    world_info: Optional[str] = None
    voice: Optional[str] = None
    traits: Optional[list[str]] = None


class PersonaCreate(BaseModel):
    name: str
    kind: Optional[str] = None
    core: Optional[str] = None
    style: Optional[str] = None
    voice: Optional[str] = None
    traits: list[str] = []


class PersonaUpdate(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    core: Optional[str] = None
    style: Optional[str] = None
    voice: Optional[str] = None
    traits: Optional[list[str]] = None


class MemberAdd(BaseModel):
    member_type: str
    member_id: int


class TodoCreate(BaseModel):
    title: str
    due_time: Optional[str] = None
    dueAt: Optional[str] = None
    priority: str = "med"
    notes: Optional[str] = None
    repeat_rule: Optional[str] = None
    repeat: Optional[str] = None


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    due_time: Optional[str] = None
    dueAt: Optional[str] = None
    priority: Optional[str] = None
    notes: Optional[str] = None
    repeat_rule: Optional[str] = None
    repeat: Optional[str] = None
    status: Optional[str] = None
    done: Optional[bool] = None
    result: Optional[str] = None


class TodoReorder(BaseModel):
    ordered_ids: list[int]


class UserCreate(BaseModel):
    display_name: Optional[str] = None
    displayName: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    avatarUrl: Optional[str] = None


class UserRead(BaseModel):
    id: int
    display_name: str
    avatar_url: Optional[str] = None
    created_at: str


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    displayName: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    avatarUrl: Optional[str] = None


class AIEnabledUpdate(BaseModel):
    enabled: bool


class MemoryFactPatch(BaseModel):
    content: Optional[str] = None
    predicate: Optional[str] = None
    confidence: Optional[float] = None


class MemoryFactCreate(BaseModel):
    predicate: str
    content: str
    confidence: Optional[float] = None


class PersonaNotePatch(BaseModel):
    content: Optional[str] = None
