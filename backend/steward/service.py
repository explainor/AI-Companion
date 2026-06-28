from typing import Any

from sqlmodel import Session, col, select

from ..core.transport import transport
from ..models import Channel, MemoryFact, Message, Persona, PersonaCard
from ..chat.context_assembler import owner_private_scope_key
from ..tools.sqlite_store import SQLiteToolStore
from .agent import run_steward_agent


class StewardService:
    def __init__(self, session: Session):
        self.session = session
        self.tool_store = SQLiteToolStore(session)

    def run_for_user_message(
        self,
        channel_id: int,
        recent: list[Message],
        user_content: str,
        persona_names: dict[int, str],
    ) -> None:
        steward = self.session.exec(select(Persona).where(Persona.is_system == 1)).first()
        if not steward:
            return
        open_todos = self.tool_store.list_todos(status="pending")
        calls = run_steward_agent(
            self.session,
            steward,
            open_todos,
            recent,
            user_content,
            persona_names,
        )
        self.apply_tool_calls(channel_id, calls, steward, recent)

    def apply_tool_calls(
        self,
        channel_id: int,
        calls: list[dict[str, Any]],
        steward: Persona | None = None,
        recent: list[Message] | None = None,
    ) -> None:
        recent = recent or []
        source_message = next((message for message in reversed(recent) if message.author_type == "human"), None)
        owner_user_id = self._owner_user_id(steward, source_message)
        for call in calls:
            name = call["name"]
            data = call.get("input", {})
            if name == "create_todo" and data.get("title"):
                self.tool_store.create_todo(
                    title=data["title"],
                    due_time=data.get("due_time"),
                    source_channel=channel_id,
                )
            elif name == "update_todo":
                self.tool_store.update_todo(
                    data.get("todo_id"),
                    {"title": data.get("title"), "due_time": data.get("due_time")},
                )
            elif name == "complete_todo":
                self.tool_store.complete_todo(data.get("todo_id"), data.get("result"))
            elif name == "write_memo" and data.get("content"):
                self.tool_store.write_memo(data["content"])
                self._write_owner_fact(steward, owner_user_id, "memo", data["content"], source_message)
            elif name == "upsert_habit" and data.get("name") and data.get("schedule"):
                self.tool_store.upsert_habit(data["name"], data["schedule"])
                self._write_owner_fact(
                    steward,
                    owner_user_id,
                    "habit",
                    f"{data['name']}；schedule={data['schedule']}",
                    source_message,
                )
            elif name == "log_habit" and data.get("habit_id"):
                self.tool_store.log_habit(data["habit_id"], data.get("value"))
            elif name == "update_style_profile" and data.get("fields"):
                self._write_owner_fact(steward, owner_user_id, "style", data["fields"], source_message, supersede=True)
            elif name == "add_disclosure_rule" and data.get("rule"):
                self._write_owner_fact(steward, owner_user_id, "disclosure_rule", data["rule"], source_message)

    def run_dock_message(
        self,
        channel_id: int,
        recent: list[Message],
        user_content: str,
        persona_names: dict[int, str],
    ) -> dict[str, Any]:
        steward = self.session.exec(select(Persona).where(Persona.is_system == 1)).first()
        if not steward:
            raise RuntimeError("Steward persona is missing")
        open_todos = self.tool_store.list_todos(status="pending")
        calls = run_steward_agent(
            self.session,
            steward,
            open_todos,
            recent,
            user_content,
            persona_names,
        )
        self.apply_tool_calls(channel_id, calls, steward, recent)
        content = self.dock_reply_text(user_content)
        return {"persona": steward, "content": content}

    def dock_reply_text(self, user_content: str) -> str:
        pending = self.tool_store.list_todos(status="pending")
        text = user_content.strip()
        if any(key in text for key in ["还有啥", "还有什么", "待办", "没做"]):
            if not pending:
                return "目前没有未完成事项。"
            items = "；".join(
                f"{todo.title}{'（' + todo.due_time + '）' if todo.due_time else ''}"
                for todo in pending[:6]
            )
            return f"当前未完成事项有：{items}。"
        if any(key in text for key in ["改到", "改成", "推迟", "提前", "完成", "取消"]):
            return "我已检查并更新账本；你可以在右侧事项模块确认。"
        if pending:
            return f"我在。当前还有 {len(pending)} 条未完成事项，需要我帮你整理或调整的话直接说。"
        return "我在。当前账本是清爽的，有安排我会帮你记住。"

    def proactivity_tick(self) -> dict[str, Any]:
        pending = self.tool_store.list_todos(status="pending")
        candidates = [todo for todo in pending if todo.due_time]
        if not candidates:
            return {
                "enabled": True,
                "candidate_count": 0,
                "pushed": False,
                "message": "无临近或带时间的待办，跳过模型与提醒。",
            }
        dock = self.steward_channel()
        steward = self.session.exec(select(Persona).where(Persona.is_system == 1)).first()
        if not dock or not steward:
            return {
                "enabled": True,
                "candidate_count": len(candidates),
                "pushed": False,
                "message": "未找到管家 dock，无法推送。",
            }
        summary = "；".join(
            f"{todo.title}{'（' + todo.due_time + '）' if todo.due_time else ''}"
            for todo in candidates[:3]
        )
        message = Message(
            channel_id=dock.id,
            sender="persona",
            persona_id=steward.id,
            author_type="ai",
            content=f"提醒一下：{summary}。需要调整时间或标记完成，直接告诉我。",
            ai_enabled_snapshot=bool(dock.ai_enabled),
        )
        self.session.add(message)
        self.session.commit()
        self.session.refresh(message)
        transport.push_nowait(
            dock.id,
            {
                "type": "proactive",
                "message": {
                    "id": message.id,
                    "channel_id": message.channel_id,
                    "sender": message.sender,
                    "persona_id": message.persona_id,
                    "persona_name": steward.name,
                    "content": message.content,
                    "created_at": message.created_at,
                    "status": message.status,
                    "chunk_group": message.chunk_group,
                },
            },
        )
        return {
            "enabled": True,
            "candidate_count": len(candidates),
            "pushed": True,
            "channel_id": dock.id,
        }

    def steward_channel(self) -> Channel | None:
        return self.session.exec(
            select(Channel).where(Channel.type == "steward", Channel.is_system == 1)
        ).first()

    def _owner_user_id(self, steward: Persona | None, source_message: Message | None) -> int | None:
        if steward and steward.id:
            card = self.session.get(PersonaCard, steward.id)
            if card and card.owner_user_id:
                return card.owner_user_id
        return source_message.author_user_id if source_message else None

    def _write_owner_fact(
        self,
        steward: Persona | None,
        owner_user_id: int | None,
        predicate: str,
        content: str,
        source_message: Message | None,
        supersede: bool = False,
    ) -> None:
        if not steward or not steward.id or not owner_user_id or not source_message or not source_message.id:
            return
        supersedes_id = None
        scope_key = owner_private_scope_key(owner_user_id, steward.id)
        if supersede:
            previous = self.session.exec(
                select(MemoryFact)
                .where(
                    MemoryFact.scope_type == "owner-private",
                    MemoryFact.scope_key == scope_key,
                    MemoryFact.predicate == predicate,
                )
                .order_by(col(MemoryFact.created_at).desc())
            ).first()
            supersedes_id = previous.id if previous else None
        fact = MemoryFact(
            scope_type="owner-private",
            scope_key=scope_key,
            subject_type="user",
            subject_id=owner_user_id,
            predicate=predicate,
            content=content.strip(),
            source_message_id=source_message.id,
            supersedes_id=supersedes_id,
        )
        self.session.add(fact)
        self.session.commit()
