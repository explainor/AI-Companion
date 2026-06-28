import logging
import re

from sqlmodel import Session, col, select

from ..models import Message

logger = logging.getLogger(__name__)


def parse_trigger_terms(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [term.strip() for term in raw.split(",") if term.strip()]


def should_retrieve_archive(content: str, trigger_terms: list[str]) -> tuple[bool, str | None]:
    for term in trigger_terms:
        if not term:
            continue
        if term.startswith("re:"):
            pattern = term.removeprefix("re:")
            if re.search(pattern, content):
                return True, term
            continue
        if term in content:
            return True, term
    return False, None


def retrieve_archive_snippets(
    session: Session,
    channel_id: int,
    query: str,
    limit: int = 4,
    exclude_recent_ids: set[int] | None = None,
) -> list[Message]:
    terms = [term for term in re.split(r"\s+", query.strip()) if len(term) >= 2]
    statement = select(Message).where(Message.channel_id == channel_id)
    if exclude_recent_ids:
        statement = statement.where(col(Message.id).not_in(exclude_recent_ids))
    if terms:
        term_filters = [col(Message.content).contains(term) for term in terms[:4]]
        statement = statement.where(*term_filters)
    rows = session.exec(statement.order_by(col(Message.id).desc()).limit(limit)).all()
    return list(reversed(rows))


def log_retrieval_gate(channel_id: int, message_id: int | None, trigger_term: str) -> None:
    logger.warning(
        "archive retrieval gate matched channel_id=%s message_id=%s trigger_term=%s",
        channel_id,
        message_id,
        trigger_term,
    )
