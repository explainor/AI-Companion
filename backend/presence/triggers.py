import json
import random
from dataclasses import dataclass
from typing import Any

from litellm import completion
from sqlmodel import Session

from ..core.config import get_setting, resolve_model
from ..core.llm import provider_ready
from .context import PresenceContext


@dataclass
class ConsiderResult:
    considered: bool
    reason: str


def should_consider(ctx: PresenceContext, cfg: dict[str, Any], session: Session) -> ConsiderResult:
    if not _bool(cfg, "presence.enabled", True):
        return ConsiderResult(False, "disabled")
    if not ctx.last_human_msg:
        return ConsiderResult(False, "no_human_msg")
    if ctx.last_mentions_ai:
        return ConsiderResult(True, "mention")
    if ctx.last_names_ai:
        return ConsiderResult(True, "named")
    if ctx.seconds_since_last_ai_msg < _int(cfg, "presence.cooldown_seconds", 90):
        return ConsiderResult(False, "cooldown")
    if ctx.ai_msgs_in_last_10_human >= _int(cfg, "presence.max_per_10_human_msgs", 2):
        return ConsiderResult(False, "ceiling")
    if ctx.seconds_since_join < _int(cfg, "presence.silence_on_startup_seconds", 30):
        return ConsiderResult(False, "warmup")
    if random.random() > _float(cfg, "presence.base_interjection_prob", 0.08):
        return ConsiderResult(False, "below_base_rate")
    return cheap_moment_gate(ctx, cfg, session)


def cheap_moment_gate(ctx: PresenceContext, cfg: dict[str, Any], session: Session) -> ConsiderResult:
    model = _model_from_setting(session, cfg.get("presence.gate_model"), "model.chat_cheap")
    if not provider_ready(model):
        return ConsiderResult(True, "fallback_gate")
    prompt = (
        "判断现在这个 AI 是否适合插一句话。只看最近几条。\n"
        "适合插话的信号：明显冷场/两人都没接话、有人提了个问题没人答得上、出现可以轻松接梗的点。\n"
        "不适合：两人聊得正热、话题私密、刚有人说完一句完整的话还没等对方回。\n"
        '只输出 JSON，无其他文字：{"ok": true|false, "reason": "<=6字"}\n'
        f"最近对话：\n{format_recent_messages(ctx)}"
    )
    try:
        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
        )
        raw = response.choices[0].message.content or ""
        data = json.loads(_json_slice(raw))
        ok = bool(data.get("ok"))
        reason = str(data.get("reason") or "cheap_gate")[:24]
        return ConsiderResult(ok, reason if ok else f"cheap_{reason}")
    except Exception:
        return ConsiderResult(False, "cheap_error")


def format_recent_messages(ctx: PresenceContext) -> str:
    lines = []
    for message in ctx.recent_messages:
        if message.author_type == "human":
            who = ctx.human_names.get(message.author_user_id or 0, "真人")
        else:
            who = ctx.persona_name
        lines.append(f"{who}: {message.content}")
    return "\n".join(lines)


def load_presence_config(session: Session) -> dict[str, str]:
    keys = [
        "presence.enabled",
        "presence.base_interjection_prob",
        "presence.cooldown_seconds",
        "presence.max_per_10_human_msgs",
        "presence.silence_on_startup_seconds",
        "presence.gate_model",
        "presence.generate_model",
        "presence.tone",
        "presence.recent_window",
    ]
    return {key: get_setting(session, key, "") or "" for key in keys}


def _model_from_setting(session: Session, raw: str | None, fallback_key: str) -> str | None:
    key = raw or fallback_key
    if key.startswith("model."):
        return resolve_model(session, key.removeprefix("model."))
    return key


def _json_slice(raw: str) -> str:
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end >= start:
        return raw[start : end + 1]
    return raw


def _bool(cfg: dict[str, Any], key: str, default: bool) -> bool:
    value = str(cfg.get(key, str(default))).lower()
    return value in {"1", "true", "yes", "on"}


def _int(cfg: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(cfg.get(key) or default)
    except (TypeError, ValueError):
        return default


def _float(cfg: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(cfg.get(key) or default)
    except (TypeError, ValueError):
        return default

