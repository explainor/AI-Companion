from typing import Any

from sqlmodel import Session, select

from ..core.transport import transport
from ..models import Channel, MemoryFact, Message, Persona, PersonaCard
from ..chat.context_assembler import owner_private_scope_key
from ..tools.sqlite_store import SQLiteToolStore
from .agent import run_steward_agent
from .predicates import MEMORY_PREDICATES


def resolve_supersedes(
    session: Session,
    scope_type: str,
    scope_key: str,
    predicate: str,
    new_fact_id: int,
) -> None:
    """
    对 overwrite 类 predicate：将同 scope + 同 predicate 的旧事实
    supersedes_id 设为 new_fact_id，标记为已过期。
    """
    if MEMORY_PREDICATES.get(predicate, {}).get("update_behavior") != "overwrite":
        return
    old_facts = session.exec(
        select(MemoryFact).where(
            MemoryFact.scope_type == scope_type,
            MemoryFact.scope_key == scope_key,
            MemoryFact.predicate == predicate,
            MemoryFact.supersedes_id == None,  # noqa: E711
            MemoryFact.id != new_fact_id,
        )
    ).all()
    for fact in old_facts:
        fact.supersedes_id = new_fact_id
        session.add(fact)
    session.commit()


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
        memory_fact_count = 0
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
            elif name == "write_memory_fact" and data.get("predicate") and data.get("content"):
                if memory_fact_count >= 3:
                    continue
                if self._write_owner_fact(
                    steward,
                    owner_user_id,
                    data["predicate"],
                    data["content"],
                    source_message,
                    confidence=data.get("confidence"),
                ):
                    memory_fact_count += 1
            elif name == "write_memo" and data.get("content"):
                self.tool_store.write_memo(data["content"])
            elif name == "upsert_habit" and data.get("name") and data.get("schedule"):
                self.tool_store.upsert_habit(data["name"], data["schedule"])
            elif name == "log_habit" and data.get("habit_id"):
                self.tool_store.log_habit(data["habit_id"], data.get("value"))
            elif name == "update_style_profile" and data.get("fields"):
                if memory_fact_count < 3 and self._write_owner_fact(
                    steward,
                    owner_user_id,
                    "pref.response_style",
                    data["fields"],
                    source_message,
                ):
                    memory_fact_count += 1
            elif name == "add_disclosure_rule" and data.get("rule"):
                if memory_fact_count < 3 and self._write_owner_fact(
                    steward,
                    owner_user_id,
                    "pref.topic_avoid",
                    data["rule"],
                    source_message,
                ):
                    memory_fact_count += 1

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
        confidence: Any = None,
    ) -> bool:
        if not steward or not steward.id or not owner_user_id or not source_message or not source_message.id:
            return False
        predicate = predicate.strip()
        content = content.strip()
        if predicate not in MEMORY_PREDICATES or not content:
            return False
        scope_key = owner_private_scope_key(owner_user_id, steward.id)
        try:
            confidence_value = float(confidence) if confidence is not None else 1.0
        except (TypeError, ValueError):
            confidence_value = 1.0
        confidence_value = min(1.0, max(0.0, confidence_value))
        fact = MemoryFact(
            scope_type="owner-private",
            scope_key=scope_key,
            subject_type="user",
            subject_id=owner_user_id,
            predicate=predicate,
            content=content[:50],
            source_message_id=source_message.id,
            confidence=confidence_value,
        )
        self.session.add(fact)
        self.session.commit()
        self.session.refresh(fact)
        if fact.id is not None:
            resolve_supersedes(self.session, fact.scope_type, fact.scope_key, predicate, fact.id)
        return True
