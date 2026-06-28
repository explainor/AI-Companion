from fastapi import HTTPException
from sqlmodel import Session, col, select

from ..models import Channel, ChannelMember, Persona, PersonaCard, User, now_iso


def normalize_member_type(member_type: str) -> str:
    if member_type in {"persona", "agent", "ai"}:
        return "agent"
    if member_type in {"human", "user"}:
        return "human"
    raise HTTPException(status_code=400, detail="member_type must be human or agent")


def agent_display_name(session: Session, persona: Persona) -> str:
    card = session.get(PersonaCard, persona.id)
    if card and card.owner_user_id:
        owner = session.get(User, card.owner_user_id)
        owner_name = owner.display_name if owner else f"用户#{card.owner_user_id}"
        return f"{owner_name}的AI·{persona.name}"
    return persona.name


def member_display_name(session: Session, member: ChannelMember) -> str:
    member_type = normalize_member_type(member.member_type)
    if member_type == "human":
        user = session.get(User, member.member_id or member.user_id)
        return user.display_name if user else f"用户#{member.member_id or member.user_id or '未知'}"
    persona = session.get(Persona, member.member_id or member.persona_id)
    return agent_display_name(session, persona) if persona else f"AI#{member.member_id or member.persona_id or '未知'}"


def list_active_members(session: Session, channel: Channel | int) -> list[ChannelMember]:
    channel_id = channel.id if isinstance(channel, Channel) else channel
    return session.exec(
        select(ChannelMember)
        .where(ChannelMember.channel_id == channel_id, ChannelMember.active == True)  # noqa: E712
        .order_by(ChannelMember.id)
    ).all()


def list_active_humans(session: Session, channel: Channel | int) -> list[User]:
    members = [
        member
        for member in list_active_members(session, channel)
        if normalize_member_type(member.member_type) == "human"
    ]
    users = []
    for member in members:
        user = session.get(User, member.member_id or member.user_id)
        if user:
            users.append(user)
    return users


def list_candidate_agents(session: Session, channel: Channel | int) -> list[Persona]:
    members = [
        member
        for member in list_active_members(session, channel)
        if normalize_member_type(member.member_type) == "agent"
    ]
    personas = []
    for member in members:
        persona = session.get(Persona, member.member_id or member.persona_id)
        if persona and not persona.is_system:
            personas.append(persona)
    return personas


def find_member(
    session: Session,
    channel_id: int,
    member_type: str,
    member_id: int,
) -> ChannelMember | None:
    member_type = normalize_member_type(member_type)
    return session.exec(
        select(ChannelMember).where(
            ChannelMember.channel_id == channel_id,
            ChannelMember.member_type == member_type,
            ChannelMember.member_id == member_id,
        )
    ).first()


def add_member(
    session: Session,
    channel: Channel,
    member_type: str,
    member_id: int,
    added_by_user_id: int | None,
) -> ChannelMember:
    member_type = normalize_member_type(member_type)
    _validate_member_target(session, member_type, member_id)
    _enforce_private_agent_owner(session, member_type, member_id, added_by_user_id)
    existing = find_member(session, channel.id, member_type, member_id)
    if existing:
        existing.active = True
        existing.left_at = None
        existing.added_by_user_id = added_by_user_id
        _sync_legacy_columns(existing)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    member = ChannelMember(
        channel_id=channel.id,
        member_type=member_type,
        member_id=member_id,
        persona_id=member_id if member_type == "agent" else None,
        user_id=member_id if member_type == "human" else None,
        added_by_user_id=added_by_user_id,
        active=True,
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def remove_member(
    session: Session,
    channel: Channel,
    member_type: str,
    member_id: int,
    requested_by_user_id: int | None,
) -> None:
    member_type = normalize_member_type(member_type)
    _enforce_private_agent_owner(session, member_type, member_id, requested_by_user_id)
    member = find_member(session, channel.id, member_type, member_id)
    if not member or not member.active:
        raise HTTPException(status_code=404, detail="Member not found")
    member.active = False
    member.left_at = now_iso()
    session.add(member)
    session.commit()


def _sync_legacy_columns(member: ChannelMember) -> None:
    if normalize_member_type(member.member_type) == "agent":
        member.persona_id = member.member_id
        member.user_id = None
    else:
        member.user_id = member.member_id
        member.persona_id = None


def _validate_member_target(session: Session, member_type: str, member_id: int) -> None:
    if member_type == "human":
        if not session.get(User, member_id):
            raise HTTPException(status_code=404, detail="User not found")
        return
    persona = session.get(Persona, member_id)
    if not persona or persona.is_system:
        raise HTTPException(status_code=404, detail="Persona not found")


def _enforce_private_agent_owner(
    session: Session,
    member_type: str,
    member_id: int,
    requested_by_user_id: int | None,
) -> None:
    if member_type != "agent":
        return
    card = session.get(PersonaCard, member_id)
    if not card or not card.owner_user_id:
        return
    if card.owner_user_id != requested_by_user_id:
        raise HTTPException(status_code=403, detail="Only the owner can add or remove this private AI")


def active_agent_ids(session: Session, channel_id: int) -> list[int]:
    return [
        member.member_id or member.persona_id
        for member in session.exec(
            select(ChannelMember).where(
                ChannelMember.channel_id == channel_id,
                ChannelMember.active == True,  # noqa: E712
                col(ChannelMember.member_type).in_(["agent", "persona"]),
            )
        ).all()
        if member.member_id or member.persona_id
    ]
