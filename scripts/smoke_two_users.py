import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.chat.service import ChatService
from backend.db import engine
from backend.main import app
from backend.models import Channel, ChannelMember, InterjectionDecision, Message, Persona, User
from backend.presence.triggers import format_recent_messages
from backend.presence.policy import InterjectionPolicy


def main() -> None:
    with TestClient(app) as client:
        user_a = client.post("/api/users", json={"display_name": "smoke-user-a"}).json()
        user_b = client.post("/api/users", json={"display_name": "smoke-user-b"}).json()
        persona = client.get("/api/personas").json()[0]
        channel = client.post(
            "/api/channels",
            json={
                "type": "group",
                "title": "smoke-two-user-channel",
                "persona_ids": [persona["id"]],
                "user_ids": [user_a["id"], user_b["id"]],
            },
        ).json()

        for user, text in (
            (user_a, "smoke user a message"),
            (user_b, "smoke user b message"),
        ):
            response = client.post(
                f"/api/channels/{channel['id']}/messages",
                headers={"X-User-Id": str(user["id"])},
                json={"content": text},
            )
            response.raise_for_status()

    with Session(engine) as session:
        db_channel = session.get(Channel, channel["id"])
        db_persona = session.get(Persona, persona["id"])
        recent = ChatService(session).last_messages(db_channel.id)
        ctx = ChatService(session).build_presence_context(
            db_channel,
            db_persona,
            recent,
            {"presence.recent_window": "12"},
        )
        rows = session.exec(
            select(Message).where(Message.channel_id == db_channel.id).order_by(Message.id)
        ).all()
        author_ids = [row.author_user_id for row in rows if row.author_type == "human"]
        assert author_ids == [user_a["id"], user_b["id"]], author_ids
        assert "smoke-user-a" in ctx.participants_label
        assert "smoke-user-b" in ctx.participants_label
        rendered = format_recent_messages(ctx)
        assert "smoke-user-a" in rendered
        assert "smoke-user-b" in rendered
        identity_ctx = ChatService(session).build_presence_context(
            db_channel,
            db_persona,
            recent + [
                Message(
                    channel_id=db_channel.id,
                    sender="user",
                    author_type="human",
                    author_user_id=user_a["id"],
                    content="我是谁",
                )
            ],
            {"presence.recent_window": "12"},
        )
        reply = InterjectionPolicy(session, {"presence.generate_model": "model.chat_strong"}).generate_reply(
            identity_ctx
        )
        assert reply is not None
        assert "smoke-user-a" in reply
        assert "smoke-user-b" in reply
        assert "跑" not in reply and "法拉利" not in reply and "妹子" not in reply
        print("OK: two users are distinct in messages and AI presence context")
        print(ctx.participants_label)
        print(rendered)
        print(reply)

        cleanup(session, db_channel, [user_a["id"], user_b["id"]])


def cleanup(session: Session, channel: Channel, user_ids: list[int]) -> None:
    for row in session.exec(
        select(InterjectionDecision).where(InterjectionDecision.channel_id == channel.id)
    ).all():
        session.delete(row)
    for row in session.exec(select(Message).where(Message.channel_id == channel.id)).all():
        session.delete(row)
    for row in session.exec(select(ChannelMember).where(ChannelMember.channel_id == channel.id)).all():
        session.delete(row)
    session.delete(channel)
    for user_id in user_ids:
        user = session.get(User, user_id)
        if user:
            session.delete(user)
    session.commit()


if __name__ == "__main__":
    main()
