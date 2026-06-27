from abc import ABC, abstractmethod
from typing import Any, Optional

from sqlmodel import Session

from ..models import (
    Channel,
    Habit,
    HabitLog,
    Memo,
    Message,
    Persona,
    PersonaNote,
    Todo,
)


class ToolStore(ABC):
    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    def update_todo(self, todo_id: int, fields: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def complete_todo(self, todo_id: int, result: Optional[str] = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_todo(self, todo_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def reorder_todos(self, ordered_ids: list[int]) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_todos(self, status: Optional[str] = None) -> list[Todo]:
        raise NotImplementedError

    @abstractmethod
    def write_memo(self, content: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def list_memos(self) -> list[Memo]:
        raise NotImplementedError

    @abstractmethod
    def upsert_habit(self, name: str, schedule: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def log_habit(
        self,
        habit_id: int,
        value: Optional[float] = None,
        ts: Optional[str] = None,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    def habit_stats(self, habit_id: int, range_name: str) -> dict[str, Any]:
        raise NotImplementedError


class MemoryStore(ABC):
    @abstractmethod
    def list_notes(self, persona_id: int) -> list[PersonaNote]:
        raise NotImplementedError

    @abstractmethod
    def search(self, persona_id: int, query: str, limit: int = 8) -> list[PersonaNote]:
        raise NotImplementedError

    @abstractmethod
    def apply_tool_calls(self, persona_id: int, calls: list[dict[str, Any]]) -> None:
        raise NotImplementedError


class ChatService(ABC):
    @abstractmethod
    def create_channel(
        self,
        type_: str,
        title: Optional[str],
        persona_ids: list[int],
        user_ids: Optional[list[int]] = None,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def list_channels(self) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    def list_messages(self, channel_id: int) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    def handle_user_message(self, channel_id: int, content: str, user_id: int) -> list[Any]:
        raise NotImplementedError


class Transport(ABC):
    @abstractmethod
    async def push(self, channel_id: int, event: dict[str, Any]) -> None:
        raise NotImplementedError
