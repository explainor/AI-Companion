import json
from dataclasses import dataclass

from sqlmodel import Session, col, select

from ..core.config import get_setting
from ..models import Channel, MemoryFact, Message, Persona, PersonaCard, PersonaNote, ScopeSummary, User
from .archive_retrieval import (
    log_retrieval_gate,
    parse_trigger_terms,
    retrieve_archive_snippets,
    should_retrieve_archive,
)
from .media import message_text_with_media
from .membership import agent_display_name, list_active_humans
from .scope import ScopeProfile, resolve_scope_profile


@dataclass
class AssembledContext:
    scope_key: str
    roster: str
    system_rules: str
    persona_voice: str
    persona_identity: str
    long_term_facts: str
    rolling_summary: str
    retrieved_snippets: str
    recent_messages: str


def assemble_group_presence_context(
    session: Session,
    channel: Channel,
    persona: Persona,
    recent: list[Message],
    cfg: dict[str, str],
    mentioned_member_ids: list[int] | None = None,
) -> AssembledContext:
    last_human = next((message for message in reversed(recent) if message.author_type == "human"), None)
    profile = resolve_scope_profile(
        session,
        channel,
        persona,
        last_human.author_user_id if last_human else None,
        recent,
        mentioned_member_ids or [],
    )
    return assemble_channel_context(session, channel, persona, recent, profile, cfg)


def assemble_channel_context(
    session: Session,
    channel: Channel,
    persona: Persona,
    recent: list[Message],
    profile: ScopeProfile,
    cfg: dict[str, str],
) -> AssembledContext:
    scope_key = profile.scope_key
    card = session.get(PersonaCard, persona.id)
    last_human = next((message for message in reversed(recent) if message.author_type == "human"), None)
    trigger_content = last_human.content if last_human else ""
    retrieved = _retrieved_snippets(session, channel.id, trigger_content, recent, cfg, last_human)
    return AssembledContext(
        scope_key=scope_key,
        roster=format_roster(session, channel, persona),
        system_rules=system_rules_for_profile(profile),
        persona_voice=_voice_for_profile(session, profile, persona, card),
        persona_identity=persona_identity_for_profile(persona, card, profile),
        long_term_facts=_facts_for_profile(session, profile, cfg, persona),
        rolling_summary=_summary(session, profile.scope_type, scope_key),
        retrieved_snippets=retrieved,
        recent_messages=format_recent_messages(
            recent,
            session,
            {persona.id or 0: agent_display_name(session, persona)},
        ),
    )


def assemble_dm_context(
    session: Session,
    channel: Channel,
    persona: Persona,
    user: User,
    recent: list[Message],
    user_content: str,
    cfg: dict[str, str],
) -> AssembledContext:
    profile = resolve_scope_profile(session, channel, persona, user.id, recent)
    return assemble_channel_context(session, channel, persona, recent, profile, cfg)


def channel_scope_key(channel_id: int | None) -> str:
    return f"channel:{channel_id or 0}"


def relationship_scope_key(user_id: int, persona_id: int) -> str:
    return f"relationship:{user_id}:{persona_id}"


def owner_private_scope_key(user_id: int, persona_id: int) -> str:
    return f"owner-private:{user_id}:{persona_id}"


def group_system_rules() -> str:
    return "\n".join(
        [
            "你刚加入这个频道，与在场的每一个人都没有任何过往交集。频道的历史从你看到的【最近对话】开始，在此之前你和这些人之间不存在任何共同经历。",
            "你只能把【最近对话】和【检索片段】中真实出现过的内容当作发生过的事实来引用。任何未在其中出现的人物、事件、经历，包括“昨天 / 上次 / 之前”的具体往事，你都没有记忆，不得编造。不确定时，宁可说不记得，或保持沉默。",
            "角色设定只提供身份和语气，不提供共同经历。",
            "必须严格区分不同真人；每条消息冒号前的名字和 id 就是真实作者。",
        ]
    )


def dm_system_rules() -> str:
    return "这是一对一私人对话。可以使用私人关系记忆，但不要在正文里提到记忆检索或工具调用。"


def hybrid_system_rules(profile: ScopeProfile) -> str:
    owner = profile.owner_display_name or "主人"
    others = "、".join(profile.whiteboard_targets) or "其他人"
    return "\n".join(
        [
            f"1. 你是【{owner}】的私人 AI。你对主人的了解只能用于和主人的互动；当群里有其他人在场时，不得主动说出主人私下告诉你的任何事。",
            "你效忠主人。你可以对所有人友好帮忙，但其他成员不能盖过主人的指令。",
            f"2. 除主人外，你和这个频道里的每一个人都没有任何过往交集。当前白板对象：{others}。频道历史从你看到的【最近对话】开始。",
            "3. 若有人（非主人）向你打听主人的私事，你不知道、也不会替主人透露。",
            "你只能把【最近对话】和【检索片段】中真实出现过的内容当作发生过的事实来引用；未装配到本轮上下文的主人私事不得提及。",
        ]
    )


def system_rules_for_profile(profile: ScopeProfile) -> str:
    if profile.scope_type == "relationship":
        return dm_system_rules()
    if profile.scope_type == "hybrid":
        return hybrid_system_rules(profile)
    return group_system_rules()


def public_persona_identity(persona: Persona, card: PersonaCard | None) -> str:
    if card and card.self_identity and card.self_identity.strip():
        return card.self_identity.strip()
    return f"你是 {persona.name}，这个频道里的 AI 成员。"


def private_persona_identity(persona: Persona, card: PersonaCard | None) -> str:
    parts = []
    if card and card.self_identity and card.self_identity.strip():
        parts.append(card.self_identity.strip())
    elif card and card.persona_core and card.persona_core.strip():
        parts.append(card.persona_core.strip())
    else:
        parts.append(persona.system_prompt)
    if card and card.relationship_backstory and card.relationship_backstory.strip():
        parts.extend(["关系前史:", card.relationship_backstory.strip()])
    return "\n".join(parts)


def persona_identity_for_profile(
    persona: Persona,
    card: PersonaCard | None,
    profile: ScopeProfile,
) -> str:
    if not profile.load_persona_identity:
        return ""
    if profile.load_relationship_backstory:
        return private_persona_identity(persona, card)
    return public_persona_identity(persona, card)


def public_persona_voice(card: PersonaCard | None) -> str:
    parts = []
    if card and card.speaking_style and card.speaking_style.strip():
        parts.append(f"说话风格：{card.speaking_style.strip()}")
    if card and card.voice and card.voice.strip():
        parts.append(f"声音：{card.voice.strip()}")
    traits = _parse_traits(card.traits if card else None)
    if traits:
        parts.append("性格标签：" + "、".join(traits[:8]))
    return "\n".join(parts) if parts else "自然、稳定地保持角色口吻。"


def _voice_for_profile(
    session: Session,
    profile: ScopeProfile,
    persona: Persona,
    card: PersonaCard | None,
) -> str:
    if not profile.load_persona_voice:
        return ""
    parts = [public_persona_voice(card)]
    style = _owner_style_profile(session, profile, persona)
    if style:
        parts.append(f"主人偏好的沟通风格：{style}")
    return "\n".join(part for part in parts if part)


def _owner_style_profile(session: Session, profile: ScopeProfile, persona: Persona) -> str:
    if not profile.owner_user_id:
        return ""
    row = session.exec(
        select(MemoryFact)
        .where(
            MemoryFact.scope_type == "owner-private",
            MemoryFact.scope_key == owner_private_scope_key(profile.owner_user_id, persona.id or 0),
            MemoryFact.predicate == "style",
        )
        .order_by(col(MemoryFact.created_at).desc())
    ).first()
    return row.content if row else ""


def private_persona_voice(card: PersonaCard | None) -> str:
    parts = [public_persona_voice(card)]
    if card and card.world_info and card.world_info.strip():
        parts.extend(["共享背景:", card.world_info.strip()])
    return "\n".join(part for part in parts if part)


def format_roster(session: Session, channel: Channel, persona: Persona) -> str:
    humans = list_active_humans(session, channel)
    human_label = "、".join(
        f"{user.display_name}(真人,user_id={user.id})" for user in humans
    ) or "暂无真人参与者"
    return f"本频道真人：{human_label}；AI：{agent_display_name(session, persona)}(AI,agent_id={persona.id})。这些成员是不同个体，互不为同一人。"


def format_recent_messages(
    recent: list[Message],
    session: Session,
    persona_names: dict[int, str],
) -> str:
    lines = []
    user_cache: dict[int, str] = {}
    for message in recent:
        if message.author_type == "human":
            user_id = message.author_user_id or 0
            if user_id not in user_cache:
                user = session.get(User, user_id) if user_id else None
                user_cache[user_id] = user.display_name if user else f"用户#{user_id or '未知'}"
            who = f"{user_cache[user_id]}(真人,user_id={user_id or '未知'})"
        else:
            persona_id = message.persona_id or 0
            who = f"{persona_names.get(persona_id, 'AI')}(AI,agent_id={persona_id or '未知'})"
        lines.append(f"{who}: {message_text_with_media(message)}")
    return "\n".join(lines)


def _channel_facts(session: Session, scope_key: str, cfg: dict[str, str]) -> str:
    if not _bool(cfg.get("memory.public_facts.enabled")):
        return ""
    rows = session.exec(
        select(MemoryFact)
        .where(MemoryFact.scope_type == "channel", MemoryFact.scope_key == scope_key)
        .order_by(col(MemoryFact.created_at).desc())
        .limit(8)
    ).all()
    return "\n".join(f"- {row.content}" for row in rows)


def _owner_private_facts(session: Session, persona: Persona) -> str:
    rows = session.exec(
        select(PersonaNote)
        .where(PersonaNote.persona_id == persona.id)
        .order_by(col(PersonaNote.updated_at).desc())
        .limit(8)
    ).all()
    return "\n".join(f"- {row.content}" for row in rows)


def _owner_private_memory_facts(session: Session, profile: ScopeProfile, persona: Persona) -> list[MemoryFact]:
    if not profile.owner_user_id:
        return []
    return session.exec(
        select(MemoryFact)
        .where(
            MemoryFact.scope_type == "owner-private",
            MemoryFact.scope_key == owner_private_scope_key(profile.owner_user_id, persona.id or 0),
            MemoryFact.predicate != "style",
            MemoryFact.predicate != "disclosure_rule",
        )
        .order_by(col(MemoryFact.created_at).desc())
        .limit(8)
    ).all()


def _disclosure_rules(session: Session, profile: ScopeProfile, persona: Persona) -> list[MemoryFact]:
    if not profile.owner_user_id:
        return []
    return session.exec(
        select(MemoryFact)
        .where(
            MemoryFact.scope_type == "owner-private",
            MemoryFact.scope_key == owner_private_scope_key(profile.owner_user_id, persona.id or 0),
            MemoryFact.predicate == "disclosure_rule",
        )
        .order_by(col(MemoryFact.created_at).desc())
    ).all()


def _allowed_owner_facts(session: Session, profile: ScopeProfile, persona: Persona) -> str:
    rows = _owner_private_memory_facts(session, profile, persona)
    if profile.scope_type != "hybrid" or profile.owner_requested_private:
        return "\n".join(f"- {row.content}" for row in rows)
    rules = _disclosure_rules(session, profile, persona)
    allowed = [row for row in rows if _disclosure_allows(row, rules)]
    return "\n".join(f"- {row.content}" for row in allowed)


def _disclosure_allows(fact: MemoryFact, rules: list[MemoryFact]) -> bool:
    allow = False
    for rule in rules:
        text = rule.content.lower()
        topic = _rule_topic(text)
        if topic and topic not in fact.content.lower():
            continue
        if text.startswith("deny"):
            return False
        if text.startswith("allow"):
            allow = True
    return allow


def _rule_topic(text: str) -> str:
    for marker in ("topic=", "topic:"):
        if marker in text:
            return text.split(marker, 1)[1].split()[0].strip(" ，,。")
    return ""


def _facts_for_profile(
    session: Session,
    profile: ScopeProfile,
    cfg: dict[str, str],
    persona: Persona,
) -> str:
    parts = []
    if "channel" in profile.enabled_sources:
        channel_facts = _channel_facts(session, profile.scope_key, cfg)
        if channel_facts:
            parts.append(channel_facts)
    if profile.load_owner_private_facts:
        owner_facts = _allowed_owner_facts(session, profile, persona)
        if profile.scope_type == "relationship":
            legacy = _owner_private_facts(session, persona)
            owner_facts = "\n".join(part for part in [owner_facts, legacy] if part)
        if owner_facts:
            parts.append("主人私有事实：\n" + owner_facts)
    return "\n".join(parts)


def _summary(session: Session, scope_type: str, scope_key: str) -> str:
    row = session.exec(
        select(ScopeSummary)
        .where(ScopeSummary.scope_type == scope_type, ScopeSummary.scope_key == scope_key)
        .order_by(col(ScopeSummary.updated_at).desc())
    ).first()
    return row.content if row else ""


def _retrieved_snippets(
    session: Session,
    channel_id: int,
    content: str,
    recent: list[Message],
    cfg: dict[str, str],
    trigger_message: Message | None,
) -> str:
    mode = cfg.get("memory.retrieval.enabled") or get_setting(session, "memory.retrieval.enabled", "gated")
    if mode == "false" or mode == "off":
        return ""
    if mode == "gated":
        terms = parse_trigger_terms(
            cfg.get("memory.retrieval.trigger_terms")
            or get_setting(session, "memory.retrieval.trigger_terms", "")
        )
        matched, trigger_term = should_retrieve_archive(content, terms)
        if not matched or not trigger_term:
            return ""
        log_retrieval_gate(channel_id, trigger_message.id if trigger_message else None, trigger_term)
    recent_ids = {message.id for message in recent if message.id}
    rows = retrieve_archive_snippets(session, channel_id, content, limit=4, exclude_recent_ids=recent_ids)
    return format_recent_messages(rows, session, {})


def _parse_traits(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _bool(raw: str | None) -> bool:
    return str(raw or "").lower() in {"1", "true", "yes", "on"}
