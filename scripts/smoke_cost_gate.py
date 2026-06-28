import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.chat.service import ChatService
from backend.core.config import get_setting, set_setting
from backend.core.llm import get_llm_call_count, record_llm_call, reset_llm_call_count
from backend.db import engine
from backend.main import app
from backend.models import (
    Channel,
    ChannelMember,
    InterjectionDecision,
    Message,
    Persona,
    PersonaCard,
    PersonaState,
    Setting,
    User,
)
from backend.presence import policy as presence_policy


def fake_completion(**_kwargs):
    record_llm_call()
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="收到。"))],
    )


def main() -> None:
    original_provider_ready = presence_policy.provider_ready
    original_completion = presence_policy.counted_completion
    presence_policy.provider_ready = lambda _model: True
    presence_policy.counted_completion = fake_completion
    created_user_ids: list[int] = []
    created_persona_ids: list[int] = []
    created_channel_ids: list[int] = []
    original_settings: dict[str, str | None] = {}
    try:
        with Session(engine) as session:
            cleanup_orphan_persona_state(session)
            for key in ("presence.baseline_interjection_rate", "presence.max_ai_replies_per_turn", "sim.enabled"):
                original_settings[key] = get_setting(session, key)
            set_setting(session, "presence.baseline_interjection_rate", "0")
            set_setting(session, "presence.max_ai_replies_per_turn", "2")
            set_setting(session, "sim.enabled", "false")

        with TestClient(app) as client:
            user = client.post("/api/users", json={"display_name": "cost-gate-user"}).json()
            other_user = client.post("/api/users", json={"display_name": "cost-gate-other"}).json()
            created_user_ids.append(user["id"])
            created_user_ids.append(other_user["id"])
            personas = []
            suffix = id(object())
            for index, name in enumerate(("同名·A", "同名·B", "特殊 符号·AI")):
                persona = client.post(
                    "/api/personas",
                    json={
                        "name": f"cost-gate-{suffix}-{name}",
                        "core": "成本门 smoke 专用 AI。",
                        "style": "短句。",
                    },
                ).json()
                personas.append(persona)
                created_persona_ids.append(persona["id"])

            channel = client.post(
                "/api/channels",
                headers={"X-User-Id": str(user["id"])},
                json={
                    "type": "group",
                    "title": "cost-gate-smoke",
                    "persona_ids": [persona["id"] for persona in personas],
                    "user_ids": [user["id"]],
                },
            ).json()
            created_channel_ids.append(channel["id"])
            agent_members = [m for m in channel["members"] if m["member_type"] == "agent"]
            agent_members.sort(key=lambda member: member["channel_member_id"])
            member_ids = [member["channel_member_id"] for member in agent_members]

            private_persona = client.post(
                "/api/personas",
                headers={"X-User-Id": str(user["id"])},
                json={
                    "name": f"cost-gate-{suffix}-private",
                    "core": "私人 AI 权限 smoke 专用。",
                    "style": "短句。",
                },
            ).json()
            created_persona_ids.append(private_persona["id"])

            forbidden_add = client.post(
                f"/api/channels/{channel['id']}/members",
                headers={"X-User-Id": str(other_user["id"])},
                json={"member_type": "agent", "member_id": private_persona["id"]},
            )
            assert forbidden_add.status_code == 403, forbidden_add.text

            first_add = client.post(
                f"/api/channels/{channel['id']}/members",
                headers={"X-User-Id": str(user["id"])},
                json={"member_type": "agent", "member_id": private_persona["id"]},
            )
            first_add.raise_for_status()
            second_add = client.post(
                f"/api/channels/{channel['id']}/members",
                headers={"X-User-Id": str(user["id"])},
                json={"member_type": "agent", "member_id": private_persona["id"]},
            )
            second_add.raise_for_status()

            forbidden_remove = client.delete(
                f"/api/channels/{channel['id']}/members/agent/{private_persona['id']}",
                headers={"X-User-Id": str(other_user["id"])},
            )
            assert forbidden_remove.status_code == 403, forbidden_remove.text

            with Session(engine) as session:
                rows = session.exec(
                    select(ChannelMember).where(
                        ChannelMember.channel_id == channel["id"],
                        ChannelMember.member_type == "agent",
                        ChannelMember.member_id == private_persona["id"],
                    )
                ).all()
                assert len(rows) == 1 and rows[0].active, rows

            reset_llm_call_count()
            for i in range(50):
                response = client.post(
                    f"/api/channels/{channel['id']}/messages",
                    headers={"X-User-Id": str(user["id"])},
                    json={"content": f"普通真人消息 {i}"},
                )
                response.raise_for_status()
                assert response.json() == []
            assert get_llm_call_count() == 0, get_llm_call_count()

            reset_llm_call_count()
            response = client.post(
                f"/api/channels/{channel['id']}/messages",
                headers={"X-User-Id": str(user["id"])},
                json={"content": "@视觉文本不参与路由", "mentioned_member_ids": [member_ids[1]]},
            )
            response.raise_for_status()
            replies = response.json()
            assert get_llm_call_count() == 1, get_llm_call_count()
            assert len(replies) == 1, replies
            assert replies[0]["persona_id"] == personas[1]["id"], replies

            reset_llm_call_count()
            response = client.post(
                f"/api/channels/{channel['id']}/messages",
                headers={"X-User-Id": str(user["id"])},
                json={
                    "content": "@多个但按结构化顺序截断",
                    "mentioned_member_ids": [member_ids[2], member_ids[0], member_ids[1]],
                },
            )
            response.raise_for_status()
            replies = response.json()
            assert get_llm_call_count() == 2, get_llm_call_count()
            assert [reply["persona_id"] for reply in replies] == [personas[2]["id"], personas[0]["id"]], replies

        with Session(engine) as session:
            channel = session.get(Channel, created_channel_ids[0])
            service = ChatService(session)
            reset_llm_call_count()
            ai_message = Message(
                channel_id=channel.id,
                sender="persona",
                persona_id=created_persona_ids[0],
                author_type="ai",
                content="@另一个AI",
            )
            replies = service.maybe_interject(channel, [ai_message], [member_ids[1]])
            assert replies == []
            assert get_llm_call_count() == 0, get_llm_call_count()

            reset_llm_call_count()
            decision = service.speaking_candidate_members(
                service.active_agent_member_rows(channel.id),
                [member_ids[1]],
                {"presence.max_ai_replies_per_turn": "2", "presence.baseline_interjection_rate": "0"},
            )
            assert [member.id for member in decision] == [member_ids[1]]
            assert get_llm_call_count() == 0, get_llm_call_count()

        print("OK: structured mention cost gate")
        print("未@且基线0: 50 messages -> 0 LLM calls")
        print("@一个: exactly 1 call")
        print("@多个超cap: deterministic first N")
        print("AI message: 0 calls")
        print("private AI add/remove: non-owner 403")
        print("idempotent add member: no duplicate rows")
    finally:
        presence_policy.provider_ready = original_provider_ready
        presence_policy.counted_completion = original_completion
        with Session(engine) as session:
            for key, value in original_settings.items():
                if value is None:
                    row = session.get(Setting, key)
                    if row:
                        session.delete(row)
                else:
                    set_setting(session, key, value)
            cleanup(session, created_channel_ids, created_persona_ids, created_user_ids)


def cleanup(
    session: Session,
    channel_ids: list[int],
    persona_ids: list[int],
    user_ids: list[int],
) -> None:
    for channel_id in channel_ids:
        for row in session.exec(
            select(InterjectionDecision).where(InterjectionDecision.channel_id == channel_id)
        ).all():
            session.delete(row)
        for row in session.exec(select(Message).where(Message.channel_id == channel_id)).all():
            session.delete(row)
        for row in session.exec(select(ChannelMember).where(ChannelMember.channel_id == channel_id)).all():
            session.delete(row)
        channel = session.get(Channel, channel_id)
        if channel:
            session.delete(channel)
    for persona_id in persona_ids:
        for row in session.exec(select(Message).where(Message.persona_id == persona_id)).all():
            session.delete(row)
        for row in session.exec(
            select(ChannelMember).where(
                col(ChannelMember.member_type).in_(["agent", "persona"]),
                ChannelMember.member_id == persona_id,
            )
        ).all():
            session.delete(row)
        card = session.get(PersonaCard, persona_id)
        if card:
            session.delete(card)
        state = session.get(PersonaState, persona_id)
        if state:
            session.delete(state)
        persona = session.get(Persona, persona_id)
        if persona:
            session.delete(persona)
    for user_id in user_ids:
        for row in session.exec(
            select(ChannelMember).where(ChannelMember.member_type == "human", ChannelMember.member_id == user_id)
        ).all():
            session.delete(row)
        user = session.get(User, user_id)
        if user:
            session.delete(user)
    session.commit()


def cleanup_orphan_persona_state(session: Session) -> None:
    persona_ids = {
        persona.id
        for persona in session.exec(select(Persona)).all()
        if persona.id is not None
    }
    for state in session.exec(select(PersonaState)).all():
        if state.persona_id not in persona_ids:
            session.delete(state)
    session.commit()


if __name__ == "__main__":
    main()
