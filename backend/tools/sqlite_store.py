from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Session, select

from ..core.interfaces import ToolStore
from ..models import Habit, HabitLog, Memo, Todo, now_iso


class SQLiteToolStore(ToolStore):
    def __init__(self, session: Session):
        self.session = session

    def create_todo(
        self,
        title: str,
        due_time: Optional[str] = None,
        priority: str = "med",
        notes: Optional[str] = None,
        repeat_rule: Optional[str] = None,
        source: str = "steward",
        source_channel: Optional[int] = None,
    ) -> int:
        todo = Todo(
            title=title,
            due_time=due_time,
            priority=priority,
            notes=notes,
            repeat_rule=repeat_rule,
            source=source,
            source_channel=source_channel,
        )
        self.session.add(todo)
        self.session.commit()
        self.session.refresh(todo)
        return todo.id

    def update_todo(self, todo_id: int, fields: dict[str, Any]) -> None:
        todo = self.session.get(Todo, todo_id)
        if not todo:
            return
        if "title" in fields and fields["title"]:
            todo.title = fields["title"]
        for key in ["due_time", "priority", "notes", "repeat_rule", "result"]:
            if key in fields:
                setattr(todo, key, fields[key])
        if "status" in fields:
            status = fields["status"]
            if status in {"pending", "done"}:
                todo.status = status
                todo.completed_at = now_iso() if status == "done" else None
        self.session.add(todo)
        self.session.commit()

    def complete_todo(self, todo_id: int, result: Optional[str] = None) -> None:
        todo = self.session.get(Todo, todo_id)
        if not todo or todo.status != "pending":
            return
        todo.status = "done"
        todo.result = result
        todo.completed_at = now_iso()
        self.session.add(todo)
        self.session.commit()

    def delete_todo(self, todo_id: int) -> None:
        todo = self.session.get(Todo, todo_id)
        if not todo:
            return
        self.session.delete(todo)
        self.session.commit()

    def reorder_todos(self, ordered_ids: list[int]) -> None:
        # SQLite implementation leaves physical order unchanged; callers sort by
        # explicit criteria. Method exists to preserve the ToolStore contract.
        return None

    def list_todos(
        self,
        status: Optional[str] = None,
        sort: str = "created",
        priority: Optional[str] = None,
    ) -> list[Todo]:
        order_by = {
            "due": Todo.due_time,
            "priority": Todo.priority,
            "created": Todo.id,
        }.get(sort, Todo.id)
        statement = select(Todo).order_by(Todo.status.desc(), order_by, Todo.id.desc())
        if status:
            statement = statement.where(Todo.status == status)
        if priority:
            statement = statement.where(Todo.priority == priority)
        return self.session.exec(statement).all()

    def write_memo(self, content: str) -> int:
        memo = Memo(content=content)
        self.session.add(memo)
        self.session.commit()
        self.session.refresh(memo)
        return memo.id

    def list_memos(self) -> list[Memo]:
        return self.session.exec(select(Memo).order_by(Memo.id.desc())).all()

    def upsert_habit(self, name: str, schedule: str) -> int:
        habit = self.session.exec(select(Habit).where(Habit.name == name)).first()
        if not habit:
            habit = Habit(name=name, schedule=schedule)
        else:
            habit.schedule = schedule
        self.session.add(habit)
        self.session.commit()
        self.session.refresh(habit)
        return habit.id

    def log_habit(
        self,
        habit_id: int,
        value: Optional[float] = None,
        ts: Optional[str] = None,
    ) -> int:
        log = HabitLog(habit_id=habit_id, value=value, ts=ts or now_iso())
        self.session.add(log)
        self.session.commit()
        self.session.refresh(log)
        return log.id

    def habit_stats(self, habit_id: int, range_name: str) -> dict[str, Any]:
        logs = self.session.exec(
            select(HabitLog).where(HabitLog.habit_id == habit_id).order_by(HabitLog.ts)
        ).all()
        return {
            "habit_id": habit_id,
            "range": range_name,
            "count": len(logs),
            "last_ts": logs[-1].ts if logs else None,
        }
