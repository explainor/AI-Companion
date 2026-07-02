import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlmodel import Session, col, select

from ..chat.memory import build_memory_store
from ..chat.context_assembler import owner_private_scope_key
from ..chat.membership import add_member, list_active_members, member_display_name, remove_member
from ..chat.service import ChatService
from ..core.config import get_setting, list_settings, set_setting
from ..core.transport import transport
from ..db import engine
from ..models import (
    Channel,
    ChannelMember,
    Habit,
    MemoryFact,
    Memo,
    Message,
    Persona,
    PersonaCard,
    PersonaNote,
    PersonaState,
    Todo,
    User,
    now_iso,
)
from ..schemas import (
    AIEnabledUpdate,
    ChannelCreate,
    ChannelRead,
    ChannelUpdate,
    MemberAdd,
    MemoryFactCreate,
    MemoryFactPatch,
    MessageCreate,
    MessageRead,
    PersonaNotePatch,
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
    UserUpdate,
)
from ..steward.service import StewardService
from ..steward.service import resolve_supersedes
from ..steward.predicates import GROUP_ORDER, MEMORY_PREDICATES
from ..metrics.service import session_metrics
from ..tools.sqlite_store import SQLiteToolStore

router = APIRouter(prefix="/api")
UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


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
    ensure_user_steward(session, user)
    return user


def safe_upload_name(filename: str | None) -> str:
    raw = filename or "upload"
    name = Path(raw).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or "upload"


def clean_avatar_url(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    if cleaned.startswith(("/uploads/", "http://", "https://", "data:image/")):
        return cleaned
    raise HTTPException(status_code=400, detail="avatar_url must be an upload path, http(s) URL, or data image")


def normalize_email(value: str | None) -> str | None:
    email = (value or "").strip().lower()
    if not email:
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="email is invalid")
    return email


def default_display_name_for_email(email: str) -> str:
    local = email.split("@", 1)[0].strip()
    return local or "用户"


def upload_suffix(filename: str, content_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix:
        return suffix
    media_type = content_type.split(";", 1)[0].lower()
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "application/pdf": ".pdf",
        "text/plain": ".txt",
    }.get(media_type, ".bin")


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


def scope_persona_id(scope_key: str) -> int | None:
    try:
        return int(scope_key.rsplit(":", 1)[-1])
    except (TypeError, ValueError):
        return None


def scope_channel_id(scope_key: str) -> int | None:
    if not scope_key.startswith("channel:"):
        return None
    try:
        return int(scope_key.split(":", 1)[1])
    except (IndexError, ValueError):
        return None


def memory_scope_label(fact: MemoryFact, persona_names: dict[int, str], channel_names: dict[int, str]) -> str:
    if fact.scope_type == "owner-private":
        persona_id = scope_persona_id(fact.scope_key)
        return f"主人私有 · {persona_names.get(persona_id or 0, fact.scope_key)}"
    if fact.scope_type == "relationship":
        persona_id = scope_persona_id(fact.scope_key)
        return f"一对一关系 · {persona_names.get(persona_id or 0, fact.scope_key)}"
    if fact.scope_type == "channel":
        channel_id = scope_channel_id(fact.scope_key)
        return f"频道 · {channel_names.get(channel_id or 0, fact.scope_key)}"
    return f"{fact.scope_type} · {fact.scope_key}"


def visible_persona_ids(session: Session, user: User) -> set[int]:
    personas = session.exec(select(Persona)).all()
    return {
        int(persona.id)
        for persona in personas
        if persona.id is not None
        and (
            persona.is_system
            or persona.kind == "entertainment"
            or number_equals(persona.creator_user_id, user.id)
        )
    }


def number_equals(left: int | None, right: int | None) -> bool:
    return left is not None and right is not None and int(left) == int(right)


def user_channel_ids(session: Session, user: User) -> set[int]:
    member_rows = session.exec(
        select(ChannelMember).where(
            ChannelMember.member_type == "human",
            ChannelMember.user_id == user.id,
            ChannelMember.active == True,  # noqa: E712
        )
    ).all()
    created_rows = session.exec(select(Channel).where(Channel.created_by_user_id == user.id)).all()
    return {
        *(int(row.channel_id) for row in member_rows if row.channel_id is not None),
        *(int(row.id) for row in created_rows if row.id is not None),
    }


def can_access_memory_fact(fact: MemoryFact, user: User, channels: set[int]) -> bool:
    if fact.scope_type == "owner-private":
        return fact.scope_key.startswith(f"owner-private:{user.id}:")
    if fact.scope_type == "relationship":
        return fact.scope_key.startswith(f"relationship:{user.id}:")
    if fact.scope_type == "channel":
        channel_id = scope_channel_id(fact.scope_key)
        return channel_id in channels
    return False


def memory_fact_payload(fact: MemoryFact, persona_names: dict[int, str], channel_names: dict[int, str]) -> dict:
    metadata = MEMORY_PREDICATES.get(fact.predicate, {})
    return {
        "id": fact.id,
        "scope_type": fact.scope_type,
        "scope_key": fact.scope_key,
        "scope_label": memory_scope_label(fact, persona_names, channel_names),
        "subject_type": fact.subject_type,
        "subject_id": fact.subject_id,
        "predicate": fact.predicate,
        "predicate_label": metadata.get("label", fact.predicate),
        "predicate_group": metadata.get("group", "其他"),
        "content": fact.content,
        "source_message_id": fact.source_message_id,
        "confidence": fact.confidence,
        "supersedes_id": fact.supersedes_id,
        "superseded": fact.supersedes_id is not None,
        "created_at": fact.created_at,
    }


def role_kind(persona: Persona, card: PersonaCard | None = None) -> str:
    if persona.kind in {"entertainment", "owned", "system"}:
        return persona.kind
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


def normalized_persona_kind(raw: str | None, default: str = "owned") -> str:
    value = (raw or default).strip()
    aliases = {
        "AI · 伙伴": "owned",
        "AI · 管家": "system",
        "系统 · 管家": "system",
        "public": "entertainment",
        "private": "owned",
    }
    value = aliases.get(value, value)
    if value not in {"entertainment", "owned", "system"}:
        raise HTTPException(status_code=400, detail="kind must be entertainment, owned, or system")
    return value


def require_persona_editable(
    session: Session,
    persona_id: int,
    x_user_id: str | None,
) -> tuple[Persona, User]:
    user = get_current_user(session, x_user_id)
    persona = session.get(Persona, persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    if persona.kind == "system" or persona.is_system:
        raise HTTPException(status_code=403, detail="System AI cannot be edited through the public API")
    if persona.kind == "entertainment":
        raise HTTPException(status_code=403, detail="Entertainment AI is read-only through the public API; clone it first")
    if persona.kind != "owned" or persona.creator_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the owner can edit this AI")
    return persona, user


def can_remove_channel_member(
    session: Session,
    channel: Channel,
    member_type: str,
    member_id: int,
    user: User,
) -> bool:
    if channel.created_by_user_id == user.id:
        return True
    normalized = "agent" if member_type in {"agent", "persona", "ai"} else "human"
    if normalized == "human":
        return member_id == user.id
    card = session.get(PersonaCard, member_id)
    return bool(card and card.owner_user_id == user.id)


def ensure_owned_quota(session: Session, user_id: int) -> None:
    limit = int(get_setting(session, "personas.max_extra_owned", "1") or "1")
    rows = session.exec(
        select(Persona)
        .join(PersonaCard, Persona.id == PersonaCard.persona_id)
        .where(
            Persona.kind == "owned",
            Persona.is_system == 0,
            PersonaCard.owner_user_id == user_id,
        )
    ).all()
    if len(rows) >= limit:
        raise HTTPException(status_code=400, detail=f"Owned AI limit reached: max_extra_owned={limit}")


def ensure_user_steward(session: Session, user: User) -> Persona | None:
    if str(get_setting(session, "personas.butler_auto_provision", "true") or "true").lower() not in {"1", "true", "yes", "on"}:
        return None
    existing = session.exec(
        select(Persona)
        .join(PersonaCard, Persona.id == PersonaCard.persona_id)
        .where(Persona.kind == "system", PersonaCard.owner_user_id == user.id)
    ).first()
    if existing:
        return existing
    name = f"{user.display_name}的管家"
    suffix = 2
    while session.exec(select(Persona).where(Persona.name == name)).first():
        name = f"{user.display_name}的管家{suffix}"
        suffix += 1
    persona = Persona(
        name=name,
        system_prompt="你是用户的贴身管家，维护事项、记忆、风格画像和披露边界。",
        model_role="steward",
        is_system=1,
        kind="system",
        creator_user_id=user.id,
        sim_config=json.dumps({"typing_delay_ms": 0, "chunking": False}, ensure_ascii=False),
    )
    session.add(persona)
    session.commit()
    session.refresh(persona)
    session.add(
        PersonaCard(
            persona_id=persona.id,
            owner_user_id=user.id,
            persona_core="贴身管家，维护客观事项账本、用户记忆、说话风格和披露边界。",
            self_identity=f"你是{user.display_name}的管家，一个效忠 owner 的系统 AI。",
            relationship_backstory="你是用户的贴身管家。",
            speaking_style="简洁、可靠、少闲聊。",
            example_dialogues="[]",
            traits="[]",
        )
    )
    session.commit()
    return persona


def ensure_persona_card(session: Session, persona: Persona) -> PersonaCard:
    card = session.get(PersonaCard, persona.id)
    if not card:
        card = PersonaCard(
            persona_id=persona.id,
            persona_core=persona.system_prompt,
            self_identity=f"你是 {persona.name}，一个 AI 伙伴。",
            relationship_backstory=persona.system_prompt,
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
        "persona_kind": persona.kind,
        "creator_user_id": persona.creator_user_id,
        "isAgent": not bool(persona.is_system),
        "is_system": persona.is_system,
        "model_role": persona.model_role,
        "model_override": persona.model_override,
        "sim_config": persona.sim_config,
        "system_prompt": persona.system_prompt,
        "owner_user_id": card.owner_user_id,
        "self_identity": card.self_identity or "",
        "relationship_backstory": card.relationship_backstory or "",
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
async def create_user(request: Request) -> User:
    payload = {}
    try:
        payload = await request.json()
    except Exception:
        try:
            form = await request.form()
            payload = dict(form)
        except Exception:
            payload = {}
    name = (
        payload.get("display_name")
        or payload.get("displayName")
        or payload.get("name")
        or request.query_params.get("display_name")
        or request.query_params.get("displayName")
        or request.query_params.get("name")
        or ""
    ).strip()
    email = normalize_email(payload.get("email") or request.query_params.get("email"))
    if not name and email:
        name = default_display_name_for_email(email)
    if not name:
        raise HTTPException(status_code=400, detail="display_name is required")
    with Session(engine) as session:
        if email:
            existing = session.exec(select(User).where(User.email == email)).first()
            if existing:
                ensure_user_steward(session, existing)
                session.refresh(existing)
                return existing
        elif existing := session.exec(select(User).where(User.display_name == name)).first():
            ensure_user_steward(session, existing)
            session.refresh(existing)
            return existing
        avatar_url = clean_avatar_url(
            payload.get("avatar_url")
            or payload.get("avatarUrl")
            or request.query_params.get("avatar_url")
            or request.query_params.get("avatarUrl")
        )
        user = User(email=email, display_name=name, avatar_url=avatar_url)
        session.add(user)
        session.commit()
        session.refresh(user)
        ensure_user_steward(session, user)
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


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> User:
    with Session(engine) as session:
        current = get_current_user(session, x_user_id)
        if current.id != user_id:
            raise HTTPException(status_code=403, detail="Cannot edit another user")
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        name = payload.display_name or payload.displayName or payload.name
        if name is not None:
            cleaned = name.strip()
            if not cleaned:
                raise HTTPException(status_code=400, detail="display_name cannot be empty")
            user.display_name = cleaned
        if payload.avatar_url is not None or payload.avatarUrl is not None:
            user.avatar_url = clean_avatar_url(payload.avatar_url if payload.avatar_url is not None else payload.avatarUrl)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@router.post("/users/{user_id}/avatar", response_model=UserRead)
async def upload_user_avatar(
    user_id: int,
    file: UploadFile = File(...),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> User:
    content_type = file.content_type or "application/octet-stream"
    if content_type.split(";", 1)[0].lower() not in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
        raise HTTPException(status_code=400, detail="avatar must be png, jpeg, gif, or webp")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    with Session(engine) as session:
        current = get_current_user(session, x_user_id)
        if current.id != user_id:
            raise HTTPException(status_code=403, detail="Cannot edit another user")
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        original_name = safe_upload_name(file.filename)
        suffix = upload_suffix(original_name, content_type)
        target_dir = UPLOAD_ROOT / "avatars" / f"user_{user_id}"
        target_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}{suffix}"
        target = target_dir / stored_name
        target.write_bytes(data)
        user.avatar_url = f"/uploads/avatars/user_{user_id}/{stored_name}"
        session.add(user)
        session.commit()
        session.refresh(user)
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
def update_persona_model(
    persona_id: int,
    payload: PersonaModelUpdate,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> Persona:
    with Session(engine) as session:
        persona, _user = require_persona_editable(session, persona_id, x_user_id)
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
                self_identity=f"你是 {persona.name}，一个 AI 伙伴。",
                relationship_backstory=persona.system_prompt,
                speaking_style="",
                example_dialogues="[]",
            )
            session.add(card)
            session.commit()
            session.refresh(card)
        return card


@router.patch("/personas/{persona_id}/card")
def update_persona_card(
    persona_id: int,
    payload: PersonaCardUpdate,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> PersonaCard:
    with Session(engine) as session:
        persona, _user = require_persona_editable(session, persona_id, x_user_id)
        card = session.get(PersonaCard, persona_id)
        if not card:
            card = PersonaCard(persona_id=persona_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            if key == "traits":
                card.traits = json.dumps(value or [], ensure_ascii=False)
            elif key == "owner_user_id":
                card.owner_user_id = value
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
def create_channel(
    payload: ChannelCreate,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> ChannelRead:
    with Session(engine) as session:
        creator = get_current_user(session, x_user_id) if x_user_id else None
        return ChatService(session).create_channel(
            payload.type,
            payload.title,
            payload.persona_ids,
            payload.user_ids,
            created_by_user_id=creator.id if creator else None,
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


@router.get("/channels/{channel_id}/members")
def get_channel_members(channel_id: int):
    with Session(engine) as session:
        channel = ChatService(session).get_channel(channel_id)
        rows = []
        for member in list_active_members(session, channel):
            owner_user_id = None
            if member.member_type in {"agent", "persona"}:
                card = session.get(PersonaCard, member.member_id or member.persona_id)
                owner_user_id = card.owner_user_id if card else None
            rows.append(
                {
                    "id": member.id,
                    "member_type": member.member_type,
                    "member_id": member.member_id,
                    "name": member_display_name(session, member),
                    "avatar_url": (
                        session.get(User, member.member_id or member.user_id).avatar_url
                        if member.member_type == "human"
                        and session.get(User, member.member_id or member.user_id)
                        else None
                    ),
                    "active": bool(member.active),
                    "added_by_user_id": member.added_by_user_id,
                    "left_at": member.left_at,
                    "owner_user_id": owner_user_id,
                }
            )
        return rows


@router.post("/channels/{channel_id}/members")
def add_channel_member(
    channel_id: int,
    payload: MemberAdd,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    with Session(engine) as session:
        user = get_current_user(session, x_user_id)
        channel = ChatService(session).get_channel(channel_id)
        member = add_member(session, channel, payload.member_type, payload.member_id, user.id)
        human = session.get(User, member.member_id or member.user_id) if member.member_type == "human" else None
        return {
            "id": member.id,
            "member_type": member.member_type,
            "member_id": member.member_id,
            "name": member_display_name(session, member),
            "avatar_url": human.avatar_url if human else None,
            "active": bool(member.active),
            "owner_user_id": (
                session.get(PersonaCard, member.member_id or member.persona_id).owner_user_id
                if member.member_type in {"agent", "persona"}
                and session.get(PersonaCard, member.member_id or member.persona_id)
                else None
            ),
        }


@router.delete("/channels/{channel_id}/members/{member_type}/{member_id}")
def remove_channel_member(
    channel_id: int,
    member_type: str,
    member_id: int,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    with Session(engine) as session:
        user = get_current_user(session, x_user_id)
        channel = ChatService(session).get_channel(channel_id)
        if not can_remove_channel_member(session, channel, member_type, member_id, user):
            raise HTTPException(status_code=403, detail="Only the channel creator or that member can remove this member")
        remove_member(session, channel, member_type, member_id, user.id)
        return {"ok": True}


@router.get("/channels/{channel_id}/events")
async def channel_events(channel_id: int):
    return StreamingResponse(
        transport.subscribe(channel_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/channels/{channel_id}/attachments")
async def upload_attachment(
    channel_id: int,
    file: UploadFile = File(...),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    content_type = file.content_type or "application/octet-stream"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    with Session(engine) as session:
        user = get_current_user(session, x_user_id)
        service = ChatService(session)
        service.get_channel(channel_id)
        service.ensure_human_member(channel_id, user.id)
    original_name = safe_upload_name(file.filename)
    suffix = upload_suffix(original_name, content_type)
    target_dir = UPLOAD_ROOT / f"channel_{channel_id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    target = target_dir / stored_name
    target.write_bytes(data)
    media_url = f"/uploads/channel_{channel_id}/{stored_name}"
    return {
        "media_url": media_url,
        "mime_type": content_type,
        "file_name": original_name,
        "size": len(data),
    }


@router.post("/channels/{channel_id}/messages", response_model=list[MessageRead])
def post_message(
    channel_id: int,
    payload: MessageCreate,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> list[MessageRead]:
    content = (payload.content or payload.text or "").strip()
    with Session(engine) as session:
        user = get_current_user(session, x_user_id)
        return ChatService(session).handle_user_message(
            channel_id,
            content,
            user.id,
            message_type=payload.type,
            media_url=payload.media_url,
            mime_type=payload.mime_type,
            file_name=payload.file_name,
            mentioned_member_ids=payload.mentioned_member_ids,
        )


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


@router.get("/memory")
def get_memory_records(
    include_superseded: bool = Query(default=False),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    with Session(engine) as session:
        user = get_current_user(session, x_user_id)
        channels = user_channel_ids(session, user)
        personas = session.exec(select(Persona)).all()
        persona_names = {int(persona.id): persona.name for persona in personas if persona.id is not None}
        channel_rows = session.exec(select(Channel)).all()
        channel_names = {
            int(channel.id): channel.title or f"Channel #{channel.id}"
            for channel in channel_rows
            if channel.id is not None
        }
        statement = select(MemoryFact).order_by(col(MemoryFact.created_at).desc()).limit(240)
        if not include_superseded:
            statement = (
                select(MemoryFact)
                .where(MemoryFact.supersedes_id == None)  # noqa: E711
                .order_by(col(MemoryFact.created_at).desc())
                .limit(240)
            )
        facts = [
            memory_fact_payload(fact, persona_names, channel_names)
            for fact in session.exec(statement).all()
            if can_access_memory_fact(fact, user, channels)
        ]
        visible_ids = visible_persona_ids(session, user)
        notes = [
            {
                "id": note.id,
                "persona_id": note.persona_id,
                "persona_name": persona_names.get(note.persona_id, f"Persona #{note.persona_id}"),
                "content": note.content,
                "updated_at": note.updated_at,
            }
            for note in session.exec(
                select(PersonaNote).order_by(col(PersonaNote.updated_at).desc()).limit(240)
            ).all()
            if note.persona_id in visible_ids
        ]
        return {"facts": facts, "notes": notes}


@router.get("/memory/predicates")
def get_memory_predicates():
    return {"predicates": MEMORY_PREDICATES, "group_order": GROUP_ORDER}


@router.post("/memory/facts")
def create_memory_fact(
    payload: MemoryFactCreate,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    predicate = payload.predicate.strip()
    content = payload.content.strip()
    if predicate not in MEMORY_PREDICATES:
        raise HTTPException(status_code=400, detail="Predicate is not in the controlled vocabulary")
    if not content:
        raise HTTPException(status_code=400, detail="Memory content cannot be empty")
    try:
        confidence = float(payload.confidence) if payload.confidence is not None else 1.0
    except (TypeError, ValueError):
        confidence = 1.0
    confidence = min(1.0, max(0.0, confidence))
    with Session(engine) as session:
        user = get_current_user(session, x_user_id)
        steward = ensure_user_steward(session, user)
        if not steward or steward.id is None:
            raise HTTPException(status_code=404, detail="Steward persona not found")
        source_message = session.exec(
            select(Message)
            .where(Message.author_type == "human", Message.author_user_id == user.id)
            .order_by(col(Message.created_at).desc())
        ).first()
        if not source_message or source_message.id is None:
            raise HTTPException(status_code=400, detail="Create at least one message before adding memory facts")
        fact = MemoryFact(
            scope_type="owner-private",
            scope_key=owner_private_scope_key(user.id, steward.id),
            subject_type="user",
            subject_id=user.id,
            predicate=predicate,
            content=content,
            source_message_id=source_message.id,
            confidence=confidence,
        )
        session.add(fact)
        session.commit()
        session.refresh(fact)
        if fact.id is not None:
            resolve_supersedes(session, fact.scope_type, fact.scope_key, predicate, fact.id)
            session.refresh(fact)
        personas = session.exec(select(Persona)).all()
        persona_names = {int(persona.id): persona.name for persona in personas if persona.id is not None}
        channels = session.exec(select(Channel)).all()
        channel_names = {int(channel.id): channel.title or f"Channel #{channel.id}" for channel in channels if channel.id is not None}
        return memory_fact_payload(fact, persona_names, channel_names)


@router.patch("/memory/facts/{fact_id}")
def patch_memory_fact(
    fact_id: int,
    payload: MemoryFactPatch,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    with Session(engine) as session:
        user = get_current_user(session, x_user_id)
        fact = session.get(MemoryFact, fact_id)
        if not fact:
            raise HTTPException(status_code=404, detail="Memory fact not found")
        if not can_access_memory_fact(fact, user, user_channel_ids(session, user)):
            raise HTTPException(status_code=403, detail="Cannot edit this memory fact")
        if payload.content is not None:
            content = payload.content.strip()
            if not content:
                raise HTTPException(status_code=400, detail="Memory content cannot be empty")
            fact.content = content
        if payload.predicate is not None:
            predicate = payload.predicate.strip()
            if predicate not in MEMORY_PREDICATES:
                raise HTTPException(status_code=400, detail="Predicate is not in the controlled vocabulary")
            fact.predicate = predicate
        if payload.confidence is not None:
            fact.confidence = min(1.0, max(0.0, float(payload.confidence)))
        session.add(fact)
        session.commit()
        session.refresh(fact)
        personas = session.exec(select(Persona)).all()
        persona_names = {int(persona.id): persona.name for persona in personas if persona.id is not None}
        channels = session.exec(select(Channel)).all()
        channel_names = {int(channel.id): channel.title or f"Channel #{channel.id}" for channel in channels if channel.id is not None}
        return memory_fact_payload(fact, persona_names, channel_names)


@router.delete("/memory/facts/{fact_id}")
def delete_memory_fact(
    fact_id: int,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    with Session(engine) as session:
        user = get_current_user(session, x_user_id)
        fact = session.get(MemoryFact, fact_id)
        if not fact:
            raise HTTPException(status_code=404, detail="Memory fact not found")
        if not can_access_memory_fact(fact, user, user_channel_ids(session, user)):
            raise HTTPException(status_code=403, detail="Cannot delete this memory fact")
        session.delete(fact)
        session.commit()
        return {"ok": True}


@router.patch("/memory/persona-notes/{note_id}")
def patch_persona_note(
    note_id: int,
    payload: PersonaNotePatch,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    with Session(engine) as session:
        user = get_current_user(session, x_user_id)
        note = session.get(PersonaNote, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Persona note not found")
        if note.persona_id not in visible_persona_ids(session, user):
            raise HTTPException(status_code=403, detail="Cannot edit this persona note")
        if payload.content is not None:
            content = payload.content.strip()
            if not content:
                raise HTTPException(status_code=400, detail="Note content cannot be empty")
            note.content = content
            note.updated_at = now_iso()
        session.add(note)
        session.commit()
        session.refresh(note)
        persona = session.get(Persona, note.persona_id)
        return {
            "id": note.id,
            "persona_id": note.persona_id,
            "persona_name": persona.name if persona else f"Persona #{note.persona_id}",
            "content": note.content,
            "updated_at": note.updated_at,
        }


@router.delete("/memory/persona-notes/{note_id}")
def delete_persona_note(
    note_id: int,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    with Session(engine) as session:
        user = get_current_user(session, x_user_id)
        note = session.get(PersonaNote, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Persona note not found")
        if note.persona_id not in visible_persona_ids(session, user):
            raise HTTPException(status_code=403, detail="Cannot delete this persona note")
        session.delete(note)
        session.commit()
        return {"ok": True}


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
            if key.startswith("admin."):
                raise HTTPException(status_code=403, detail="Admin settings can only be changed in /admin")
            saved.append(set_setting(session, key, str(value).lower() if isinstance(value, bool) else str(value)))
        return saved


@router.patch("/personas/{persona_id}")
def patch_persona(
    persona_id: int,
    payload: PersonaUpdate,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    with Session(engine) as session:
        persona, _user = require_persona_editable(session, persona_id, x_user_id)
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
        if payload.kind is not None:
            persona.kind = normalized_persona_kind(payload.kind, persona.kind)
        session.add(persona)
        session.add(card)
        session.commit()
        session.refresh(persona)
        return persona_profile(session, persona)


@router.post("/personas")
def create_persona(
    payload: PersonaCreate,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Persona name is required")
    with Session(engine) as session:
        owner = get_current_user(session, x_user_id) if x_user_id else None
        if owner:
            ensure_owned_quota(session, owner.id)
        existing = session.exec(select(Persona).where(Persona.name == name)).first()
        if existing:
            raise HTTPException(status_code=409, detail="Persona name already exists")
        persona = Persona(
            name=name,
            system_prompt=payload.core or "你是用户的 AI 伙伴，请自然、稳定地保持角色口吻。",
            model_role="chat_strong",
            is_system=0,
            kind="owned" if owner else normalized_persona_kind(payload.kind, "entertainment"),
            creator_user_id=owner.id if owner else None,
        )
        session.add(persona)
        session.commit()
        session.refresh(persona)
        card = PersonaCard(
            persona_id=persona.id,
            owner_user_id=owner.id if owner else None,
            persona_core=payload.core or persona.system_prompt,
            self_identity=f"你是 {persona.name}，一个 AI 伙伴。",
            relationship_backstory=payload.core or "",
            speaking_style=payload.style or "",
            voice=payload.voice or "",
            traits=json.dumps(payload.traits or [], ensure_ascii=False),
        )
        session.add(card)
        if not session.get(PersonaState, persona.id):
            session.add(PersonaState(persona_id=persona.id, familiarity=0))
        session.commit()
        return persona_profile(session, persona)


@router.post("/personas/{persona_id}/clone")
def clone_persona(
    persona_id: int,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    with Session(engine) as session:
        user = get_current_user(session, x_user_id)
        source = session.get(Persona, persona_id)
        if not source:
            raise HTTPException(status_code=404, detail="Persona not found")
        if source.kind != "entertainment":
            raise HTTPException(status_code=400, detail="Only entertainment AI can be cloned")
        ensure_owned_quota(session, user.id)
        source_card = ensure_persona_card(session, source)
        base_name = f"{source.name}（{user.display_name}的版本）"
        name = base_name
        suffix = 2
        while session.exec(select(Persona).where(Persona.name == name)).first():
            name = f"{base_name}{suffix}"
            suffix += 1
        clone = Persona(
            name=name,
            system_prompt=source.system_prompt,
            model=source.model,
            is_system=0,
            kind="owned",
            creator_user_id=user.id,
            model_role=source.model_role,
            model_override=source.model_override,
            sim_config=source.sim_config,
        )
        session.add(clone)
        session.commit()
        session.refresh(clone)
        session.add(
            PersonaCard(
                persona_id=clone.id,
                owner_user_id=user.id,
                persona_core=source_card.persona_core,
                self_identity=source_card.self_identity,
                relationship_backstory=source_card.relationship_backstory,
                speaking_style=source_card.speaking_style,
                example_dialogues=source_card.example_dialogues,
                world_info=source_card.world_info,
                voice=source_card.voice,
                traits=source_card.traits,
            )
        )
        if not session.get(PersonaState, clone.id):
            session.add(PersonaState(persona_id=clone.id, familiarity=0))
        session.commit()
        return persona_profile(session, clone)


@router.delete("/personas/{persona_id}")
def delete_persona(
    persona_id: int,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    with Session(engine) as session:
        persona, _user = require_persona_editable(session, persona_id, x_user_id)
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
    if key.startswith("admin."):
        raise HTTPException(status_code=403, detail="Admin settings can only be changed in /admin")
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
