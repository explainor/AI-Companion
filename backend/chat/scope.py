from dataclasses import dataclass, field

from sqlmodel import Session, col, select

from ..models import Channel, ChannelMember, Message, Persona, PersonaCard, User
from .membership import list_active_humans


@dataclass
class ScopeProfile:
    scope_type: str
    scope_key: str
    load_persona_voice: bool = True
    load_persona_identity: bool = True
    load_relationship_backstory: bool = False
    load_owner_private_facts: bool = False
    owner_user_id: int | None = None
    owner_display_name: str | None = None
    whiteboard_targets: list[str] = field(default_factory=list)
    enabled_sources: list[str] = field(default_factory=list)


def resolve_scope_profile(
    session: Session,
    channel: Channel,
    persona: Persona,
    addressed_by_user_id: int | None,
    recent: list[Message],
    mentioned_member_ids: list[int] | None = None,
) -> ScopeProfile:
    card = session.get(PersonaCard, persona.id)
    owner_user_id = card.owner_user_id if card else None
    if channel.type == "dm":
        return ScopeProfile(
            scope_type="relationship",
            scope_key=f"relationship:{addressed_by_user_id or owner_user_id or 0}:{persona.id}",
            load_relationship_backstory=True,
            load_owner_private_facts=True,
            owner_user_id=addressed_by_user_id or owner_user_id,
            owner_display_name=_owner_name(session, addressed_by_user_id or owner_user_id),
            enabled_sources=["relationship_backstory", "owner_private_facts"],
        )
    if not owner_user_id:
        return ScopeProfile(
            scope_type="channel",
            scope_key=f"channel:{channel.id}",
            enabled_sources=["channel"],
        )

    owner_name = _owner_name(session, owner_user_id)
    humans = list_active_humans(session, channel)
    whiteboard_targets = [user.display_name for user in humans if user.id != owner_user_id]
    unlocked = bool(
        addressed_by_user_id == owner_user_id
        and _persona_member_mentioned(session, channel.id or 0, persona.id or 0, mentioned_member_ids or [])
    )
    enabled_sources = ["hybrid"]
    if unlocked:
        enabled_sources.extend(["relationship_backstory", "owner_private_facts"])
    return ScopeProfile(
        scope_type="hybrid",
        scope_key=f"hybrid:{channel.id}:{owner_user_id}:{persona.id}",
        load_relationship_backstory=unlocked,
        load_owner_private_facts=unlocked,
        owner_user_id=owner_user_id,
        owner_display_name=owner_name,
        whiteboard_targets=whiteboard_targets,
        enabled_sources=enabled_sources,
    )


def _persona_member_mentioned(
    session: Session,
    channel_id: int,
    persona_id: int,
    mentioned_member_ids: list[int],
) -> bool:
    if not mentioned_member_ids:
        return False
    member = session.exec(
        select(ChannelMember).where(
            ChannelMember.channel_id == channel_id,
            ChannelMember.active == True,  # noqa: E712
            col(ChannelMember.member_type).in_(["agent", "persona"]),
            ChannelMember.member_id == persona_id,
        )
    ).first()
    return bool(member and member.id in set(mentioned_member_ids))


def _owner_name(session: Session, user_id: int | None) -> str | None:
    if not user_id:
        return None
    user = session.get(User, user_id)
    return user.display_name if user else f"用户#{user_id}"
