import json
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from ..chat.memory import build_memory_store
from ..chat.service import ChatService
from ..core.config import list_settings, set_setting
from ..core.transport import transport
from ..db import engine
from ..models import (
    Channel,
    ChannelMember,
    Habit,
    Memo,
    Message,
    Persona,
    PersonaCard,
    PersonaNote,
    PersonaState,
    Todo,
    User,
)
from ..schemas import (
    AIEnabledUpdate,
    ChannelCreate,
    ChannelRead,
    ChannelUpdate,
    MessageCreate,
    MessageRead,
    PersonaCreate,
    PersonaModelUpdate,
    PersonaCardUpdate,
    PersonaUpdate,
    SettingUpdate,
    TodoCreate,
    TodoReorder,
    TodoUpdate,
    UserCreate,
    UserRead,
)
from ..steward.service import StewardService
from ..metrics.service import compare as compare_metrics
from ..metrics.service import session_metrics
from ..tools.sqlite_store import SQLiteToolStore

router = APIRouter(prefix="/api")


def get_current_user(session: Session, x_user_id: str | None) -> User:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-Id header is required")
    try:
        user_id = int(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-User-Id must be an integer")
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def parse_traits(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def role_kind(persona: Persona, card: PersonaCard | None = None) -> str:
    if card and card.world_info:
        try:
            data = json.loads(card.world_info)
            if isinstance(data, dict) and data.get("kind"):
                return str(data["kind"])
        except json.JSONDecodeError:
            pass
    if persona.is_system:
        return "系统 · 管家"
    labels = {
        "chat_strong": "AI · 伙伴",
        "chat_cheap": "AI · 轻量伙伴",
        "steward": "AI · 管家",
    }
    return labels.get(persona.model_role, f"AI · {persona.model_role}")


def set_role_kind(card: PersonaCard, kind: str | None) -> None:
    if kind is None:
        return
    data = {}
    if card.world_info:
        try:
            existing = json.loads(card.world_info)
            if isinstance(existing, dict):
                data = existing
        except json.JSONDecodeError:
            data = {}
    data["kind"] = kind
    card.world_info = json.dumps(data, ensure_ascii=False)


def ensure_persona_card(session: Session, persona: Persona) -> PersonaCard:
    card = session.get(PersonaCard, persona.id)
    if not card:
        card = PersonaCard(
            persona_id=persona.id,
            persona_core=persona.system_prompt,
            speaking_style="",
            example_dialogues="[]",
            traits="[]",
        )
        session.add(card)
        session.commit()
        session.refresh(card)
    return card


def persona_dm_channel_id(session: Session, persona_id: int) -> int | None:
    rows = session.exec(
        select(Channel)
        .join(ChannelMember, Channel.id == ChannelMember.channel_id)
        .where(Channel.type == "dm", ChannelMember.persona_id == persona_id)
        .order_by(Channel.id)
    ).all()
    return rows[0].id if rows else None


def last_interaction_label(value: str | None) -> str:
    if not value:
        return "暂无"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    now = datetime.now(dt.tzinfo)
    if dt.date() == now.date():
        return "今天"
    if (now.date() - dt.date()).days == 1:
        return "昨天"
    return dt.strftime("%m/%d")


def persona_profile(session: Session, persona: Persona) -> dict:
    card = ensure_persona_card(session, persona)
    state = session.get(PersonaState, persona.id)
    message_count = session.exec(
        select(Message).where(Message.persona_id == persona.id)
    ).all()
    shared_tasks = session.exec(
        select(Todo)
        .join(ChannelMember, Todo.source_channel == ChannelMember.channel_id)
        .where(ChannelMember.persona_id == persona.id)
    ).all()
    last_message = session.exec(
        select(Message)
        .where(Message.persona_id == persona.id)
        .order_by(Message.created_at.desc())
    ).first()
    last_interaction = (
        state.last_interaction_at
        if state and state.last_interaction_at
        else last_message.created_at if last_message else None
    )
    core = card.persona_core or persona.system_prompt
    return {
        "id": persona.id,
        "name": persona.name,
        "avatarHue": hue_for(persona.name),
        "kind": role_kind(persona, card),
        "isAgent": not bool(persona.is_system),
        "is_system": persona.is_system,
        "model_role": persona.model_role,
        "model_override": persona.model_override,
        "sim_config": persona.sim_config,
        "system_prompt": persona.system_prompt,
        "familiarity": state.familiarity if state else 0,
        "voice": card.voice or "",
        "core": core,
        "style": card.speaking_style or "",
        "traits": parse_traits(card.traits),
        "channelId": persona_dm_channel_id(session, persona.id),
        "stats": {
            "messages": compact_count(len(message_count)),
            "sharedTasks": str(len(shared_tasks)),
            "lastInteraction": last_interaction_label(last_interaction),
        },
    }


def compact_count(value: int) -> str:
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return str(value)


@router.post("/users", response_model=UserRead)
def create_user(payload: UserCreate) -> User:
    name = payload.display_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="display_name is required")
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.display_name == name)).first()
        if existing:
            return existing
        user = User(display_name=name)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@router.get("/users", response_model=list[UserRead])
def list_users() -> list[User]:
    with Session(engine) as session:
        return session.exec(select(User).order_by(User.id)).all()


@router.get("/users/{user_id}", response_model=UserRead)
def get_user(user_id: int) -> User:
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user


@router.get("/personas")
def list_personas(include_system: bool = False):
    with Session(engine) as session:
        statement = select(Persona).order_by(Persona.id)
        if not include_system:
            statement = statement.where(Persona.is_system == 0)
        return [persona_profile(session, persona) for persona in session.exec(statement).all()]


@router.get("/personas/{persona_id}")
def get_persona(persona_id: int):
    with Session(engine) as session:
        persona = session.get(Persona, persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")
        return persona_profile(session, persona)


@router.patch("/personas/{persona_id}/model")
def update_persona_model(persona_id: int, payload: PersonaModelUpdate) -> Persona:
    with Session(engine) as session:
        persona = session.get(Persona, persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")
        if payload.model_role is not None:
            persona.model_role = payload.model_role
        if payload.model_override is not None:
            persona.model_override = payload.model_override or None
        if payload.sim_config is not None:
            persona.sim_config = payload.sim_config or None
        session.add(persona)
        session.commit()
        session.refresh(persona)
        return persona


@router.get("/personas/{persona_id}/card")
def get_persona_card(persona_id: int) -> PersonaCard:
    with Session(engine) as session:
        persona = session.get(Persona, persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")
        card = session.get(PersonaCard, persona_id)
        if not card:
            card = PersonaCard(
                persona_id=persona_id,
                persona_core=persona.system_prompt,
                speaking_style="",
                example_dialogues="[]",
            )
            session.add(card)
            session.commit()
            session.refresh(card)
        return card


@router.patch("/personas/{persona_id}/card")
def update_persona_card(persona_id: int, payload: PersonaCardUpdate) -> PersonaCard:
    with Session(engine) as session:
        persona = session.get(Persona, persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")
        card = session.get(PersonaCard, persona_id)
        if not card:
            card = PersonaCard(persona_id=persona_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            if key == "traits":
                card.traits = json.dumps(value or [], ensure_ascii=False)
            elif key == "world_info":
                card.world_info = value or None
            else:
                setattr(card, key, value or "")
        session.add(card)
        session.commit()
        session.refresh(card)
        return card


@router.get("/personas/{persona_id}/notes")
def get_notes(persona_id: int):
    with Session(engine) as session:
        persona = session.get(Persona, persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")
        return build_memory_store(session).list_notes(persona_id)


@router.get("/persona-state")
def list_persona_state() -> list[PersonaState]:
    with Session(engine) as session:
        return session.exec(select(PersonaState).order_by(PersonaState.persona_id)).all()


@router.post("/channels", response_model=ChannelRead)
def create_channel(payload: ChannelCreate) -> ChannelRead:
    with Session(engine) as session:
        return ChatService(session).create_channel(
            payload.type, payload.title, payload.persona_ids, payload.user_ids
        )


@router.get("/channels", response_model=list[ChannelRead])
def list_channels() -> list[ChannelRead]:
    with Session(engine) as session:
        return ChatService(session).list_channels()


@router.patch("/channels/{channel_id}", response_model=ChannelRead)
def update_channel(channel_id: int, payload: ChannelUpdate) -> ChannelRead:
    with Session(engine) as session:
        return ChatService(session).update_channel(
            channel_id,
            title=payload.title,
            pinned=payload.pinned,
            archived=payload.archived,
        )


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: int):
    with Session(engine) as session:
        ChatService(session).delete_channel(channel_id)
        return {"ok": True}


@router.delete("/channels/{channel_id}/messages")
def clear_channel_messages(channel_id: int):
    with Session(engine) as session:
        ChatService(session).clear_channel_messages(channel_id)
        return {"ok": True}


@router.get("/channels/{channel_id}/messages", response_model=list[MessageRead])
def get_messages(channel_id: int) -> list[MessageRead]:
    with Session(engine) as session:
        return ChatService(session).list_messages(channel_id)


@router.get("/channels/{channel_id}/events")
async def channel_events(channel_id: int):
    return StreamingResponse(
        transport.subscribe(channel_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/channels/{channel_id}/messages", response_model=list[MessageRead])
def post_message(
    channel_id: int,
    payload: MessageCreate,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> list[MessageRead]:
    content = (payload.content or payload.text or "").strip()
    with Session(engine) as session:
        user = get_current_user(session, x_user_id)
        return ChatService(session).handle_user_message(channel_id, content, user.id)


@router.post("/channels/{channel_id}/ai_enabled")
def set_channel_ai_enabled(channel_id: int, payload: AIEnabledUpdate):
    with Session(engine) as session:
        channel = session.get(Channel, channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        channel.ai_enabled = payload.enabled
        session.add(channel)
        session.commit()
        session.refresh(channel)
        return {"ai_enabled": bool(channel.ai_enabled)}


@router.get("/channels/{channel_id}/metrics")
def get_channel_metrics(
    channel_id: int,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
):
    with Session(engine) as session:
        if not session.get(Channel, channel_id):
            raise HTTPException(status_code=404, detail="Channel not found")
        return session_metrics(session, channel_id, start, end)


@router.get("/channels/{channel_id}/metrics/compare")
def get_channel_metrics_compare(channel_id: int):
    with Session(engine) as session:
        if not session.get(Channel, channel_id):
            raise HTTPException(status_code=404, detail="Channel not found")
        return compare_metrics(session, channel_id)


@router.get("/todos")
def get_todos(
    status: str | None = Query(default=None),
    sort: str = "created",
    priority: str | None = None,
) -> list[Todo]:
    with Session(engine) as session:
        return SQLiteToolStore(session).list_todos(status=status, sort=sort, priority=priority)


@router.post("/todos")
def create_todo(payload: TodoCreate) -> Todo:
    with Session(engine) as session:
        store = SQLiteToolStore(session)
        todo_id = store.create_todo(
            title=payload.title.strip(),
            due_time=payload.due_time or payload.dueAt,
            priority=payload.priority,
            notes=payload.notes,
            repeat_rule=payload.repeat_rule or payload.repeat,
            source="user",
        )
        return session.get(Todo, todo_id)


@router.patch("/todos/{todo_id}")
def update_todo(todo_id: int, payload: TodoUpdate) -> Todo:
    with Session(engine) as session:
        store = SQLiteToolStore(session)
        fields = payload.model_dump(exclude_unset=True)
        if "dueAt" in fields:
            fields["due_time"] = fields.pop("dueAt")
        if "repeat" in fields:
            fields["repeat_rule"] = fields.pop("repeat")
        if "done" in fields:
            fields["status"] = "done" if fields.pop("done") else "pending"
        store.update_todo(todo_id, fields)
        todo = session.get(Todo, todo_id)
        if not todo:
            raise HTTPException(status_code=404, detail="Todo not found")
        return todo


@router.delete("/todos/{todo_id}")
def delete_todo(todo_id: int):
    with Session(engine) as session:
        SQLiteToolStore(session).delete_todo(todo_id)
        return {"ok": True}


@router.post("/todos/reorder")
def reorder_todos(payload: TodoReorder):
    with Session(engine) as session:
        SQLiteToolStore(session).reorder_todos(payload.ordered_ids)
        return {"ok": True}


@router.get("/memos")
def get_memos():
    with Session(engine) as session:
        return SQLiteToolStore(session).list_memos()


@router.get("/habits")
def get_habits() -> list[Habit]:
    with Session(engine) as session:
        return session.exec(select(Habit).order_by(Habit.id)).all()


@router.get("/relations")
def get_relations():
    with Session(engine) as session:
        states = session.exec(select(PersonaState).order_by(PersonaState.persona_id)).all()
        rows = []
        for state in states:
            persona = session.get(Persona, state.persona_id)
            rows.append(
                {
                    "id": str(state.persona_id),
                    "name": persona.name if persona else f"Persona #{state.persona_id}",
                    "role": persona.model_role if persona else "伙伴",
                    "avatarHue": hue_for(persona.name if persona else str(state.persona_id)),
                    "familiarity": state.familiarity,
                }
            )
        if rows:
            return rows
        personas = session.exec(select(Persona).where(Persona.is_system == 0).order_by(Persona.id)).all()
        return [
            {
                "id": str(persona.id),
                "name": persona.name,
                "role": persona.model_role,
                "avatarHue": hue_for(persona.name),
                "familiarity": 0,
            }
            for persona in personas
        ]


@router.get("/schedule")
def get_schedule(date: str | None = None):
    with Session(engine) as session:
        todos = SQLiteToolStore(session).list_todos(sort="due")
        rows = []
        for todo in todos:
            if not todo.due_time:
                continue
            state = "done" if todo.status == "done" else "todo"
            rows.append(
                {
                    "id": str(todo.id),
                    "at": todo.due_time,
                    "title": todo.title,
                    "state": state,
                    "tag": priority_label(todo.priority),
                }
            )
        return rows


@router.get("/steward/brief")
def get_steward_brief():
    with Session(engine) as session:
        todos = SQLiteToolStore(session).list_todos()
        pending = [todo for todo in todos if todo.status != "done"]
        high = [todo for todo in pending if todo.priority == "high"]
        greeting = greeting_for_now()
        note = f"今天还有 {len(pending)} 件待办，其中 {len(high)} 件高优先级。要我帮你把明天的安排也排一下吗？"
        return {
            "note": note,
            "greeting": greeting,
            "quickChips": ["梳理明天", "只看高优先级"],
        }


@router.get("/steward/messages")
def get_steward_messages():
    with Session(engine) as session:
        steward_channel = ChatService(session).list_channels()
        channel = next((item for item in steward_channel if item.type == "steward"), None)
        if not channel:
            return {"messages": [], "hasMore": False}
        messages = ChatService(session).list_messages(channel.id)
        return {"messages": [message.model_dump() for message in messages], "hasMore": False}


@router.get("/habits/{habit_id}/stats")
def get_habit_stats(habit_id: int, range: str = "all"):
    with Session(engine) as session:
        return SQLiteToolStore(session).habit_stats(habit_id, range)


@router.get("/settings")
def get_settings():
    with Session(engine) as session:
        return list_settings(session)


@router.patch("/settings")
def patch_settings(payload: dict):
    with Session(engine) as session:
        flattened = flatten_settings(payload)
        saved = []
        for key, value in flattened.items():
            saved.append(set_setting(session, key, str(value).lower() if isinstance(value, bool) else str(value)))
        return saved


@router.patch("/personas/{persona_id}")
def patch_persona(persona_id: int, payload: PersonaUpdate):
    with Session(engine) as session:
        persona = session.get(Persona, persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")
        if payload.name is not None:
            persona.name = payload.name.strip() or persona.name
        if payload.core is not None:
            persona.system_prompt = payload.core or persona.system_prompt
        card = ensure_persona_card(session, persona)
        if payload.core is not None:
            card.persona_core = payload.core or ""
        if payload.style is not None:
            card.speaking_style = payload.style or ""
        if payload.voice is not None:
            card.voice = payload.voice or ""
        if payload.traits is not None:
            card.traits = json.dumps(payload.traits, ensure_ascii=False)
        set_role_kind(card, payload.kind)
        session.add(persona)
        session.add(card)
        session.commit()
        session.refresh(persona)
        return persona_profile(session, persona)


@router.post("/personas")
def create_persona(payload: PersonaCreate):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Persona name is required")
    with Session(engine) as session:
        existing = session.exec(select(Persona).where(Persona.name == name)).first()
        if existing:
            raise HTTPException(status_code=409, detail="Persona name already exists")
        persona = Persona(
            name=name,
            system_prompt=payload.core or "你是用户的 AI 伙伴，请自然、稳定地保持角色口吻。",
            model_role="chat_strong",
            is_system=0,
        )
        session.add(persona)
        session.commit()
        session.refresh(persona)
        card = PersonaCard(
            persona_id=persona.id,
            persona_core=payload.core or persona.system_prompt,
            speaking_style=payload.style or "",
            voice=payload.voice or "",
            traits=json.dumps(payload.traits or [], ensure_ascii=False),
        )
        set_role_kind(card, payload.kind or "AI · 伙伴")
        session.add(card)
        session.add(PersonaState(persona_id=persona.id, familiarity=0))
        session.commit()
        return persona_profile(session, persona)


@router.delete("/personas/{persona_id}")
def delete_persona(persona_id: int):
    with Session(engine) as session:
        persona = session.get(Persona, persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")
        if persona.is_system:
            raise HTTPException(status_code=400, detail="System persona cannot be deleted")
        for model in (PersonaCard, PersonaState):
            row = session.get(model, persona_id)
            if row:
                session.delete(row)
        for row in session.exec(select(PersonaNote).where(PersonaNote.persona_id == persona_id)).all():
            session.delete(row)
        for row in session.exec(select(ChannelMember).where(ChannelMember.persona_id == persona_id)).all():
            session.delete(row)
        session.delete(persona)
        session.commit()
        return {"ok": True}


@router.put("/settings/{key}")
def put_setting(key: str, payload: SettingUpdate):
    with Session(engine) as session:
        return set_setting(session, key, payload.value)


@router.post("/steward/proactivity/tick")
def proactivity_tick():
    with Session(engine) as session:
        return StewardService(session).proactivity_tick()


def hue_for(value: str) -> int:
    total = 0
    for char in value:
        total = (total * 31 + ord(char)) % 360
    return total or 95


def priority_label(priority: str) -> str:
    return {"high": "高优先级", "med": "中优先级", "low": "低优先级"}.get(priority, "中优先级")


def greeting_for_now() -> str:
    hour = datetime.now().hour
    if hour < 6:
        return "夜深了"
    if hour < 12:
        return "早上好"
    if hour < 18:
        return "下午好"
    return "晚上好"


def flatten_settings(payload: dict, prefix: str = "") -> dict[str, object]:
    flat: dict[str, object] = {}
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(flatten_settings(value, path))
        elif key != "personas":
            flat[path] = value
    return flat
