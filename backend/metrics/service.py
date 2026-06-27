from collections import Counter
from datetime import datetime, timezone
from itertools import pairwise
from typing import Iterable

from sqlmodel import Session, select

from ..models import InterjectionDecision, Message


def session_metrics(
    session: Session,
    channel_id: int,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    messages = _messages(session, channel_id, start, end)
    decisions = _decisions(session, channel_id, start, end)
    return metrics_over(messages, decisions)


def compare(session: Session, channel_id: int) -> dict:
    messages = _messages(session, channel_id, None, None)
    decisions = _decisions(session, channel_id, None, None)
    on_msgs = [message for message in messages if bool(message.ai_enabled_snapshot)]
    off_msgs = [message for message in messages if not bool(message.ai_enabled_snapshot)]
    grouped = _decisions_by_snapshot(decisions, messages)
    return {
        "ai_on": metrics_over(on_msgs, grouped[True]),
        "ai_off": metrics_over(off_msgs, grouped[False]),
    }


def metrics_over(messages: list[Message], decisions: list[InterjectionDecision]) -> dict:
    human_human = 0
    human_ai = 0
    for prev, cur in pairwise(messages):
        if (
            prev.author_type == "human"
            and cur.author_type == "human"
            and prev.author_user_id
            and cur.author_user_id
            and prev.author_user_id != cur.author_user_id
        ):
            human_human += 1
        elif {prev.author_type, cur.author_type} == {"human", "ai"}:
            human_ai += 1

    considered = sum(1 for decision in decisions if decision.considered)
    spoke = sum(1 for decision in decisions if decision.spoke)
    n_messages = len(messages)
    per_human = Counter(
        str(message.author_user_id)
        for message in messages
        if message.author_type == "human" and message.author_user_id is not None
    )
    return {
        "human_human_turns": human_human,
        "human_ai_turns": human_ai,
        "hh_to_ha_ratio": (human_human / human_ai) if human_ai else None,
        "ai_interjection_rate": (spoke / considered) if considered else 0.0,
        "ai_silence_rate": (1 - spoke / n_messages) if n_messages else 1.0,
        "human_msgs_per_human": dict(per_human),
        "n_messages": n_messages,
        "considered": considered,
        "spoke": spoke,
    }


def _messages(session: Session, channel_id: int, start: str | None, end: str | None) -> list[Message]:
    statement = select(Message).where(Message.channel_id == channel_id).order_by(Message.created_at)
    if start:
        statement = statement.where(Message.created_at >= _iso(start))
    if end:
        statement = statement.where(Message.created_at < _iso(end))
    return session.exec(statement).all()


def _decisions(
    session: Session,
    channel_id: int,
    start: str | None,
    end: str | None,
) -> list[InterjectionDecision]:
    statement = (
        select(InterjectionDecision)
        .where(InterjectionDecision.channel_id == channel_id)
        .order_by(InterjectionDecision.created_at)
    )
    if start:
        statement = statement.where(InterjectionDecision.created_at >= _iso(start))
    if end:
        statement = statement.where(InterjectionDecision.created_at < _iso(end))
    return session.exec(statement).all()


def _decisions_by_snapshot(
    decisions: Iterable[InterjectionDecision],
    messages: list[Message],
) -> dict[bool, list[InterjectionDecision]]:
    grouped: dict[bool, list[InterjectionDecision]] = {True: [], False: []}
    sorted_messages = sorted(messages, key=lambda message: message.created_at)
    for decision in decisions:
        previous = None
        for message in sorted_messages:
            if message.created_at <= decision.created_at:
                previous = message
            else:
                break
        if previous is not None:
            grouped[bool(previous.ai_enabled_snapshot)].append(decision)
    return grouped


def _iso(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()
