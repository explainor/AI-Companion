import hashlib
from pathlib import Path
from typing import Any

from sqlmodel import Session, col, select

from ..core.config import get_setting
from ..core.interfaces import MemoryStore
from ..models import PersonaNote, now_iso


class SQLiteMemoryStore(MemoryStore):
    def __init__(self, session: Session):
        self.session = session

    def list_notes(self, persona_id: int) -> list[PersonaNote]:
        return self.session.exec(
            select(PersonaNote)
            .where(PersonaNote.persona_id == persona_id)
            .order_by(PersonaNote.updated_at.desc())
            .limit(20)
        ).all()

    def search(self, persona_id: int, query: str, limit: int = 8) -> list[PersonaNote]:
        terms = [term for term in query.strip().split() if term]
        statement = select(PersonaNote).where(PersonaNote.persona_id == persona_id)
        if terms:
            for term in terms[:4]:
                statement = statement.where(col(PersonaNote.content).contains(term))
        rows = self.session.exec(
            statement.order_by(PersonaNote.updated_at.desc()).limit(limit)
        ).all()
        if rows or not terms:
            return rows
        return self.list_notes(persona_id)[:limit]

    def apply_tool_calls(self, persona_id: int, calls: list[dict[str, Any]]) -> None:
        for call in calls:
            name = call["name"]
            data = call.get("input", {})
            if name == "add_note" and data.get("content"):
                self.session.add(PersonaNote(persona_id=persona_id, content=data["content"]))
            elif name == "update_note":
                note = self.session.get(PersonaNote, data.get("note_id"))
                if note and note.persona_id == persona_id and data.get("content"):
                    note.content = data["content"]
                    note.updated_at = now_iso()
                    self.session.add(note)
            elif name == "delete_note":
                note = self.session.get(PersonaNote, data.get("note_id"))
                if note and note.persona_id == persona_id:
                    self.session.delete(note)
        self.session.commit()


class Mem0MemoryStore(SQLiteMemoryStore):
    """Mem0-backed memory with SQLite notes kept as a local compatibility cache."""

    def __init__(self, session: Session):
        super().__init__(session)
        self.client = self._build_client()

    def search(self, persona_id: int, query: str, limit: int = 8) -> list[PersonaNote]:
        if not self.client:
            return super().search(persona_id, query, limit)
        try:
            result = self.client.search(
                query=query,
                user_id="local-user",
                agent_id=self._agent_id(persona_id),
                limit=limit,
            )
            rows = self._normalize_search(persona_id, result)
            return rows[:limit] or super().search(persona_id, query, limit)
        except Exception:
            return super().search(persona_id, query, limit)

    def apply_tool_calls(self, persona_id: int, calls: list[dict[str, Any]]) -> None:
        super().apply_tool_calls(persona_id, calls)
        if not self.client:
            return
        for call in calls:
            name = call["name"]
            data = call.get("input", {})
            content = data.get("content")
            try:
                if name in {"add_note", "update_note"} and content:
                    self.client.add(
                        content,
                        user_id="local-user",
                        agent_id=self._agent_id(persona_id),
                        metadata={"persona_id": persona_id, "source": "persona_tool"},
                    )
            except Exception:
                continue

    def _build_client(self):
        try:
            from mem0 import Memory
        except Exception:
            return None

        base_path = get_setting(self.session, "memory.mem0.path", ".mem0") or ".mem0"
        path = Path(base_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent.parent / path
        config = {
            "vector_store": {
                "provider": get_setting(self.session, "memory.mem0.vector_store", "chroma"),
                "config": {"path": str(path)},
            },
        }
        try:
            return Memory.from_config(config)
        except Exception:
            return None

    def _normalize_search(self, persona_id: int, result: Any) -> list[PersonaNote]:
        items = result.get("results", result) if isinstance(result, dict) else result
        rows: list[PersonaNote] = []
        for item in items or []:
            if isinstance(item, dict):
                content = item.get("memory") or item.get("text") or item.get("content")
                raw_id = str(item.get("id") or item.get("memory_id") or content or "")
            else:
                content = str(item)
                raw_id = content
            if not content:
                continue
            numeric_id = int(hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:8], 16)
            rows.append(
                PersonaNote(
                    id=numeric_id,
                    persona_id=persona_id,
                    content=content,
                    updated_at=now_iso(),
                )
            )
        return rows

    def _agent_id(self, persona_id: int) -> str:
        return f"persona-{persona_id}"


def build_memory_store(session: Session) -> MemoryStore:
    if get_setting(session, "memory.backend", "sqlite") == "mem0":
        return Mem0MemoryStore(session)
    return SQLiteMemoryStore(session)
