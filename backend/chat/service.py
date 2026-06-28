import json
import random
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlmodel import Session, col, select

from ..core.config import get_setting
from ..core.interfaces import ChatService as ChatServiceInterface
from ..core.transport import transport
from ..models import (
    Channel,
    ChannelMember,
    InterjectionDecision,
    Message,
    Persona,
    PersonaCard,
    PersonaState,
    User,
)
from ..presence.context import PresenceContext
from ..presence.policy import InterjectionPolicy
from ..presence.triggers import load_presence_config
from ..schemas import ChannelRead, MessageRead
from ..steward.service import StewardService
from .agents import run_persona_agent
from .membership import (
    add_member,
    agent_display_name,
    list_active_humans,
    list_candidate_agents,
)
from .memory import build_memory_store
from .relationship import update_relationship_state


class ChatService(ChatServiceInterface):
    def __init__(self, session: Session):
        self.session = session
        self.memory = build_memory_store(session)

    def create_channel(
        self,
        type_: str,
        title: Optional[str],
        persona_ids: list[int],
        user_ids: Optional[list[int]] = None,
        created_by_user_id: int | None = None,
    ) -> ChannelRead:
        user_ids = user_ids or []
        if type_ not in {"dm", "group"}:
            raise HTTPException(status_code=400, detail="type must be dm or group")
        if type_ == "dm" and len(persona_ids) != 1:
            raise HTTPException(status_code=400, detail="dm requires exactly one persona")
        if type_ == "group" and not (persona_ids or user_ids):
            raise HTTPException(status_code=400, detail="group requires members")
        personas = self.session.exec(
            select(Persona).where(col(Persona.id).in_(persona_ids), Persona.is_system == 0)
        ).all()
        if len(personas) != len(set(persona_ids)):
            raise HTTPException(status_code=400, detail="invalid persona_ids")
        if user_ids:
            users = self.session.exec(select(User).where(col(User.id).in_(user_ids))).all()
            if len(users) != len(set(user_ids)):
                raise HTTPException(status_code=400, detail="invalid user_ids")
        channel = Channel(type=type_, title=title, created_by_user_id=created_by_user_id)
        self.session.add(channel)
        self.session.commit()
        self.session.refresh(channel)
        for persona_id in persona_ids:
            add_member(self.session, channel, "agent", persona_id, created_by_user_id)
        for user_id in user_ids:
            add_member(self.session, channel, "human", user_id, created_by_user_id)
        self.session.refresh(channel)
        return self.read_channel(channel)

    def list_channels(self) -> list[ChannelRead]:
        channels = self.session.exec(select(Channel).order_by(Channel.id)).all()
        return [self.read_channel(channel) for channel in channels]

    def list_messages(self, channel_id: int) -> list[MessageRead]:
        self.get_channel(channel_id)
        messages = self.session.exec(
            select(Message).where(Message.channel_id == channel_id).order_by(Message.id)
        ).all()
        return [self.read_message(message) for message in messages]

    def handle_user_message(
        self,
        channel_id: int,
        content: str,
        user_id: int,
        message_type: str = "text",
        media_url: str | None = None,
        mime_type: str | None = None,
        file_name: str | None = None,
        mentioned_member_ids: list[int] | None = None,
    ) -> list[MessageRead]:
        content = content.strip()
        message_type = message_type or "text"
        if not content and not media_url:
            raise HTTPException(status_code=400, detail="content is required")
        channel = self.get_channel(channel_id)
        self.ensure_human_member(channel_id, user_id)
        user_message = Message(
            channel_id=channel_id,
            sender="user",
            author_type="human",
            author_user_id=user_id,
            message_type=message_type,
            media_url=media_url,
            mime_type=mime_type,
            file_name=file_name,
            content=content,
            ai_enabled_snapshot=bool(channel.ai_enabled),
        )
        self.session.add(user_message)
        self.session.commit()
        self.session.refresh(user_message)
        transport.push_nowait(
            channel_id,
            {"type": "message", "message": self.read_message(user_message).model_dump()},
        )

        recent = self.last_messages(channel_id)
        names = self.persona_names()
        if channel.is_system and channel.type == "steward":
            dock_reply = StewardService(self.session).run_dock_message(
                channel_id, recent, content, names
            )
            return self.persist_persona_reply(
                channel_id, dock_reply["persona"], dock_reply["content"]
            )

        members = self.channel_members(channel_id)
        if channel.type == "dm":
            responders = members
        else:
            return self.maybe_interject(channel, recent, mentioned_member_ids or [])
        replies: list[MessageRead] = []

        for persona in responders:
            notes = self.memory.search(persona.id, content)
            state = self.session.get(PersonaState, persona.id)
            card = self.session.get(PersonaCard, persona.id)
            reply_text, calls = run_persona_agent(
                self.session, persona, notes, state, card, recent, content, names
            )
            self.memory.apply_tool_calls(persona.id, calls)
            memory_contents = [
                call.get("input", {}).get("content", "")
                for call in calls
                if call.get("name") in {"add_note", "update_note"}
            ]
            update_relationship_state(self.session, persona.id, content, memory_contents)
            replies.extend(self.persist_persona_reply(channel_id, persona, reply_text))

        StewardService(self.session).run_for_user_message(channel_id, recent, content, names)
        return replies

    def maybe_interject(
        self,
        channel: Channel,
        recent: list[Message],
        mentioned_member_ids: list[int] | None = None,
    ) -> list[MessageRead]:
        decision = InterjectionDecision(channel_id=channel.id)
        try:
            if not channel.ai_enabled:
                decision.trigger_reason = "ai_disabled"
                return []
            last_message = recent[-1] if recent else None
            if not last_message or last_message.author_type != "human":
                decision.trigger_reason = "non_human_message"
                return []
            candidate_members = self.active_agent_member_rows(channel.id)
            if not candidate_members:
                decision.trigger_reason = "no_persona"
                return []
            cfg = load_presence_config(self.session)
            policy = InterjectionPolicy(self.session, cfg)
            selected_members = self.speaking_candidate_members(
                candidate_members,
                mentioned_member_ids or [],
                cfg,
            )
            selected = [
                self.session.get(Persona, member.member_id or member.persona_id)
                for member in selected_members
            ]
            selected = [persona for persona in selected if persona]
            if not selected:
                decision.trigger_reason = "not_addressed"
                return []
            decision.considered = True
            decision.trigger_reason = "addressed" if mentioned_member_ids else "baseline"
            replies: list[MessageRead] = []
            total_latency = 0
            for persona in selected:
                ctx = self.build_presence_context(channel, persona, recent, cfg, mentioned_member_ids or [])
                t0 = now_ms()
                reply = policy.generate_reply(ctx)
                total_latency += now_ms() - t0
                if reply is None:
                    continue
                replies.extend(self.persist_persona_reply(channel.id, persona, reply))
            decision.latency_ms = total_latency
            if not replies:
                decision.suppressed_reason = "not_worth_saying"
                return []
            decision.spoke = True
            return replies
        finally:
            self.session.add(decision)
            self.session.commit()

    def speaking_candidates(
        self,
        candidates: list[Persona],
        recent: list[Message],
        cfg: dict[str, str],
    ) -> list[Persona]:
        last_message = recent[-1] if recent else None
        if not last_message or last_message.author_type != "human":
            return []
        try:
            baseline = float(cfg.get("presence.baseline_interjection_rate") or 0)
        except ValueError:
            baseline = 0
        if baseline <= 0 or random.random() >= baseline:
            return []
        return candidates[: min(1, self.max_ai_replies_per_turn(cfg))]

    def speaking_candidate_members(
        self,
        candidate_members: list[ChannelMember],
        mentioned_member_ids: list[int],
        cfg: dict[str, str],
    ) -> list[ChannelMember]:
        cap = self.max_ai_replies_per_turn(cfg)
        by_id = {member.id: member for member in candidate_members if member.id is not None}
        ordered = []
        seen = set()
        for member_id in mentioned_member_ids:
            if member_id in seen:
                continue
            seen.add(member_id)
            member = by_id.get(member_id)
            if member:
                ordered.append(member)
            if len(ordered) >= cap:
                return ordered
        if mentioned_member_ids:
            return ordered
        try:
            baseline = float(cfg.get("presence.baseline_interjection_rate") or 0)
        except ValueError:
            baseline = 0
        if baseline <= 0 or random.random() >= baseline:
            return []
        return candidate_members[: min(1, cap)]

    def max_ai_replies_per_turn(self, cfg: dict[str, str]) -> int:
        try:
            return max(0, int(cfg.get("presence.max_ai_replies_per_turn") or 1))
        except ValueError:
            return 1

    def active_agent_member_rows(self, channel_id: int) -> list[ChannelMember]:
        return self.session.exec(
            select(ChannelMember).where(
                ChannelMember.channel_id == channel_id,
                ChannelMember.active == True,  # noqa: E712
                col(ChannelMember.member_type).in_(["agent", "persona"]),
            ).order_by(ChannelMember.id)
        ).all()

    def persist_persona_reply(
        self,
        channel_id: int,
        persona: Persona,
        reply_text: str,
    ) -> list[MessageRead]:
        reply_text = self.sanitize_persona_reply(reply_text)
        chunks = self.reply_chunks(persona, reply_text)
        chunk_group = str(uuid.uuid4()) if len(chunks) > 1 else None
        replies: list[MessageRead] = []
        for chunk in chunks:
            delay_ms = self.typing_delay_ms(persona, chunk)
            if delay_ms > 0:
                transport.push_nowait(
                    channel_id,
                    {
                        "type": "typing",
                        "persona_id": persona.id,
                        "persona_name": persona.name,
                        "delay_ms": delay_ms,
                    },
                )
                time.sleep(delay_ms / 1000)
            reply = Message(
                channel_id=channel_id,
                sender="persona",
                persona_id=persona.id,
                author_type="ai",
                content=chunk,
                chunk_group=chunk_group,
                ai_enabled_snapshot=bool(self.get_channel(channel_id).ai_enabled),
            )
            self.session.add(reply)
            self.session.commit()
            self.session.refresh(reply)
            read = self.read_message(reply)
            replies.append(read)
            transport.push_nowait(
                channel_id,
                {"type": "message", "message": read.model_dump()},
            )
        return replies

    def sanitize_persona_reply(self, text: str) -> str:
        cleaned = text.strip()
        internal_terms = (
            "记忆",
            "工具",
            "tool",
            "add_note",
            "update_note",
            "delete_note",
            "后台",
        )
        cleaned = re.sub(
            r"[（(][^（）()]{0,120}(?:记忆|工具|tool|add_note|update_note|delete_note|后台)[^（）()]{0,120}[）)]",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        lines = []
        for line in cleaned.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if any(term.lower() in stripped.lower() for term in internal_terms) and any(
                marker in stripped
                for marker in [
                    "已更新",
                    "更新了",
                    "已记录",
                    "记录了",
                    "不用动",
                    "看了看",
                    "检索",
                    "调用",
                    "维护",
                    "写入",
                    "保存",
                    "完成",
                ]
            ):
                continue
            lines.append(line)
        cleaned = "\n".join(lines).strip()
        cleaned = re.sub(
            r"(^|[。！？!?]\s*)(?:哈哈，?|行，?|好，?)?(?:我)?(?:已经|已)?(?:把)?(?:记忆|后台记忆)(?:已)?(?:更新|记录|保存)(?:了|好)?[。！？!]*",
            r"\1",
            cleaned,
        )
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned or "我听到了。"

    def get_channel(self, channel_id: int) -> Channel:
        channel = self.session.get(Channel, channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        return channel

    def read_channel(self, channel: Channel) -> ChannelRead:
        member_rows = self.session.exec(
            select(ChannelMember)
            .where(ChannelMember.channel_id == channel.id, ChannelMember.active == True)  # noqa: E712
            .order_by(ChannelMember.id)
        ).all()
        personas: list[Persona] = []
        members: list[dict] = []
        for member in member_rows:
            if member.member_type == "human":
                user = self.session.get(User, member.member_id or member.user_id)
                if not user:
                    continue
                members.append(
                    {
                        "id": user.id,
                        "channel_member_id": member.id,
                        "member_type": "human",
                        "name": user.display_name,
                        "display_name": user.display_name,
                    }
                )
                continue
            persona = self.session.get(Persona, member.member_id or member.persona_id)
            if not persona:
                continue
            card = self.session.get(PersonaCard, persona.id)
            personas.append(persona)
            members.append(
                {
                    "id": persona.id,
                    "channel_member_id": member.id,
                    "member_type": "agent",
                    "name": agent_display_name(self.session, persona),
                    "raw_name": persona.name,
                    "is_system": persona.is_system,
                    "model_role": persona.model_role,
                    "model_override": persona.model_override,
                    "sim_config": persona.sim_config,
                    "owner_user_id": card.owner_user_id if card else None,
                }
            )
        title = (
            agent_display_name(self.session, personas[0])
            if channel.type == "dm" and personas
            else channel.title
        )
        return ChannelRead(
            id=channel.id,
            type=channel.type,
            title=title,
            created_at=channel.created_at,
            is_system=channel.is_system,
            pinned=channel.pinned,
            archived=channel.archived,
            ai_enabled=bool(channel.ai_enabled),
            created_by_user_id=channel.created_by_user_id,
            members=members,
        )

    def read_message(self, message: Message) -> MessageRead:
        name = None
        user_name = None
        if message.persona_id:
            persona = self.session.get(Persona, message.persona_id)
            name = agent_display_name(self.session, persona) if persona else None
        if message.author_user_id:
            user = self.session.get(User, message.author_user_id)
            user_name = user.display_name if user else None
        return MessageRead(
            id=message.id,
            channel_id=message.channel_id,
            sender=message.sender,
            persona_id=message.persona_id,
            persona_name=name,
            author_type=message.author_type or ("ai" if message.sender == "persona" else "human"),
            author_user_id=message.author_user_id,
            author_user_name=user_name,
            ai_enabled_snapshot=bool(message.ai_enabled_snapshot),
            type=message.message_type or "text",
            media_url=message.media_url,
            mime_type=message.mime_type,
            file_name=message.file_name,
            content=message.content,
            created_at=message.created_at,
            status=message.status,
            chunk_group=message.chunk_group,
        )

    def update_channel(
        self,
        channel_id: int,
        title: Optional[str] = None,
        pinned: Optional[int] = None,
        archived: Optional[int] = None,
    ) -> ChannelRead:
        channel = self.get_channel(channel_id)
        if title is not None:
            channel.title = title.strip() or channel.title
        if pinned is not None:
            channel.pinned = pinned
        if archived is not None:
            channel.archived = archived
        self.session.add(channel)
        self.session.commit()
        self.session.refresh(channel)
        return self.read_channel(channel)

    def delete_channel(self, channel_id: int) -> None:
        channel = self.get_channel(channel_id)
        if channel.is_system:
            raise HTTPException(status_code=400, detail="System channel cannot be deleted")
        messages = self.session.exec(select(Message).where(Message.channel_id == channel_id)).all()
        members = self.session.exec(
            select(ChannelMember).where(ChannelMember.channel_id == channel_id)
        ).all()
        for message in messages:
            self.session.delete(message)
        for member in members:
            self.session.delete(member)
        self.session.delete(channel)
        self.session.commit()

    def clear_channel_messages(self, channel_id: int) -> None:
        self.get_channel(channel_id)
        messages = self.session.exec(select(Message).where(Message.channel_id == channel_id)).all()
        for message in messages:
            self.session.delete(message)
        self.session.commit()

    def channel_members(self, channel_id: int) -> list[Persona]:
        return list_candidate_agents(self.session, channel_id)

    def channel_users(self, channel_id: int) -> list[User]:
        return list_active_humans(self.session, channel_id)

    def ensure_human_member(self, channel_id: int, user_id: int) -> None:
        user = self.session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        existing = self.session.exec(
            select(ChannelMember).where(
                ChannelMember.channel_id == channel_id,
                ChannelMember.member_type == "human",
                ChannelMember.member_id == user_id,
            )
        ).first()
        if existing:
            if not existing.active:
                existing.active = True
                existing.left_at = None
                self.session.add(existing)
                self.session.commit()
            return
        channel = self.get_channel(channel_id)
        add_member(self.session, channel, "human", user_id, user_id)

    def sole_ai_member(self, channel_id: int) -> Persona | None:
        members = self.channel_members(channel_id)
        return members[0] if members else None

    def build_presence_context(
        self,
        channel: Channel,
        persona: Persona,
        recent: list[Message],
        cfg: dict[str, str],
        mentioned_member_ids: list[int] | None = None,
    ) -> PresenceContext:
        try:
            window = int(cfg.get("presence.recent_window") or 12)
        except ValueError:
            window = 12
        rows = recent[-window:]
        human_names = {user.id: user.display_name for user in self.channel_users(channel.id) if user.id}
        for message in rows:
            if message.author_type != "human" or not message.author_user_id:
                continue
            if message.author_user_id in human_names:
                continue
            user = self.session.get(User, message.author_user_id)
            human_names[message.author_user_id] = (
                user.display_name if user else f"用户#{message.author_user_id}"
            )
        last_human = next((message for message in reversed(rows) if message.author_type == "human"), None)
        last_ai = next((message for message in reversed(rows) if message.author_type == "ai"), None)
        human_seen = 0
        ai_in_last_10_human = 0
        for message in reversed(rows):
            if message.author_type == "human":
                human_seen += 1
                if human_seen > 10:
                    break
            elif message.author_type == "ai":
                ai_in_last_10_human += 1
        return PresenceContext(
            channel_id=channel.id,
            persona=persona,
            card=self.session.get(PersonaCard, persona.id),
            recent_messages=rows,
            persona_name=persona.name,
            human_names=human_names,
            seconds_since_last_ai_msg=seconds_since(last_ai.created_at) if last_ai else 10_000,
            ai_msgs_in_last_10_human=ai_in_last_10_human,
            seconds_since_join=seconds_since(channel.created_at),
            last_human_msg=last_human,
            extra_context="",
            mentioned_member_ids=mentioned_member_ids or [],
        )

    def reply_chunks(self, persona: Persona, text: str) -> list[str]:
        if get_setting(self.session, "sim.enabled", "true") != "true":
            return [text]
        config = self.sim_config(persona)
        if not config.get("chunking", True):
            return [text]
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        if len(paragraphs) > 1:
            return paragraphs[:4]
        if len(text) <= 140:
            return [text]
        parts = [part.strip() for part in re.split(r"(?<=[。！？!?])", text) if part.strip()]
        if len(parts) <= 1:
            return [text]
        chunks: list[str] = []
        current = ""
        for part in parts:
            if current and len(current) + len(part) > 120:
                chunks.append(current)
                current = part
            else:
                current += part
        if current:
            chunks.append(current)
        return chunks[:4]

    def typing_delay_ms(self, persona: Persona, text: str) -> int:
        if get_setting(self.session, "sim.enabled", "true") != "true":
            return 0
        config = self.sim_config(persona)
        base = int(config.get("typing_delay_ms", 500))
        if base <= 0:
            return 0
        min_delay = int(get_setting(self.session, "sim.min_delay_ms", "250") or 250)
        max_delay = int(get_setting(self.session, "sim.max_delay_ms", "1800") or 1800)
        calculated = base + min(len(text) * 8, 900)
        return max(min_delay, min(max_delay, calculated))

    def sim_config(self, persona: Persona) -> dict[str, Any]:
        if not persona.sim_config:
            return {}
        try:
            return json.loads(persona.sim_config)
        except json.JSONDecodeError:
            return {}

    def last_messages(self, channel_id: int, n: int = 20) -> list[Message]:
        rows = self.session.exec(
            select(Message)
            .where(Message.channel_id == channel_id)
            .order_by(col(Message.id).desc())
            .limit(n)
        ).all()
        return list(reversed(rows))

    def persona_names(self) -> dict[int, str]:
        personas = self.session.exec(select(Persona)).all()
        return {p.id: agent_display_name(self.session, p) for p in personas if p.id is not None}


def now_ms() -> int:
    return int(time.time() * 1000)


def seconds_since(value: str | None) -> int:
    if not value:
        return 10_000
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 10_000
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
