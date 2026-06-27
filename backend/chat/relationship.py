import json
from datetime import datetime, timezone
from typing import Iterable

from sqlmodel import Session

from ..core.config import get_setting
from ..models import PersonaState, now_iso


def relationship_summary(state: PersonaState | None) -> str:
    if not state:
        return "熟悉度: 0.00; 最近基调: 未知; 上次互动: 暂无; 里程碑: 暂无"
    milestones = _load_milestones(state.milestones)
    return (
        f"熟悉度: {state.familiarity:.2f}; "
        f"最近基调: {state.last_tone or '未知'}; "
        f"上次互动: {state.last_interaction_at or state.last_interaction or '暂无'}; "
        f"里程碑: {'; '.join(milestones[:5]) if milestones else '暂无'}"
    )


def update_relationship_state(
    session: Session,
    persona_id: int,
    user_content: str,
    memory_contents: Iterable[str],
) -> PersonaState:
    state = session.get(PersonaState, persona_id)
    if not state:
        state = PersonaState(persona_id=persona_id)

    state.familiarity = _decayed_familiarity(session, state)
    gain = _float_setting(session, "relationship.familiarity_gain", 0.04)
    max_value = _float_setting(session, "relationship.max_familiarity", 1.0)
    state.familiarity = min(max_value, state.familiarity + gain)
    state.last_tone = infer_tone(user_content)
    state.last_interaction = now_iso()
    state.last_interaction_at = state.last_interaction
    state.milestones = json.dumps(
        _merge_milestones(state.milestones, user_content, memory_contents),
        ensure_ascii=False,
    )
    session.add(state)
    session.commit()
    return state


def infer_tone(text: str) -> str:
    lowered = text.lower()
    if any(token in text for token in ["哈哈", "笑死", "牛", "可以啊"]):
        return "轻松"
    if any(token in text for token in ["焦虑", "难受", "崩", "压力"]):
        return "认真"
    if any(token in text for token in ["谢谢", "感谢", "麻烦"]):
        return "温和"
    if any(token in lowered for token in ["pb", "done", "finish"]):
        return "积极"
    return "日常"


def _decayed_familiarity(session: Session, state: PersonaState) -> float:
    timestamp = state.last_interaction_at or state.last_interaction
    if not timestamp:
        return state.familiarity
    try:
        last = datetime.fromisoformat(timestamp)
    except ValueError:
        return state.familiarity
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    days = max(0, (datetime.now(timezone.utc) - last).days)
    decay = _float_setting(session, "relationship.familiarity_decay_per_day", 0.01)
    return max(0.0, state.familiarity - days * decay)


def _merge_milestones(
    raw_milestones: str | None,
    user_content: str,
    memory_contents: Iterable[str],
) -> list[str]:
    milestones = _load_milestones(raw_milestones)
    candidates = list(memory_contents)
    if any(token in user_content for token in ["PB", "pb", "定下", "决定", "完成", "通过"]):
        candidates.append(user_content)
    for content in candidates:
        cleaned = content.strip()
        if len(cleaned) < 4 or cleaned in milestones:
            continue
        milestones.append(cleaned[:80])
    return milestones[-12:]


def _load_milestones(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in value if str(item).strip()]


def _float_setting(session: Session, key: str, default: float) -> float:
    try:
        return float(get_setting(session, key, str(default)) or default)
    except ValueError:
        return default
