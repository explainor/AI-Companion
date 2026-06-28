from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from sqlmodel import Session, select

from ..models import Setting

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

DEFAULT_MODEL_SETTINGS = {
    "model.chat_strong": "openai/deepseek-chat",
    "model.chat_cheap": "openai/qwen3.5-27b",
    "model.steward": "openai/deepseek-chat",
    "model.vision": "openai/glm-5.1",
    "model.catalog.sjtu": (
        "["
        '{"label":"DeepSeek V3.2 常规模式","model":"openai/deepseek-chat"},'
        '{"label":"DeepSeek V3.2 思考模式","model":"openai/deepseek-reasoner"},'
        '{"label":"MiniMax-M2.7","model":"openai/minimax-m2.7"},'
        '{"label":"GLM-5.1","model":"openai/glm-5.1"},'
        '{"label":"Qwen3.5-27B","model":"openai/qwen3.5-27b"}'
        "]"
    ),
    "sim.enabled": "true",
    "sim.min_delay_ms": "250",
    "sim.max_delay_ms": "1800",
    "proactivity.enabled": "false",
    "proactivity.interval_minutes": "30",
    "proactivity.speaker_persona_id": "",
    "proactivity.channel_id": "",
    "memory.backend": "sqlite",
    "memory.mem0.vector_store": "chroma",
    "memory.mem0.path": ".mem0",
    "memory.extract_every_n_messages": "4",
    "memory.public_facts.enabled": "false",
    "memory.retrieval.enabled": "gated",
    "memory.retrieval.trigger_terms": "记得,还记得,上次,之前,以前,那个,那件事,刚才说的,前面说的",
    "relationship.familiarity_gain": "0.04",
    "relationship.familiarity_decay_per_day": "0.01",
    "relationship.max_familiarity": "1.0",
    "presence.enabled": "true",
    "presence.baseline_interjection_rate": "0",
    "presence.max_ai_replies_per_turn": "1",
    "presence.base_interjection_prob": "0.08",
    "presence.cooldown_seconds": "90",
    "presence.max_per_10_human_msgs": "2",
    "presence.silence_on_startup_seconds": "30",
    "presence.gate_model": "model.chat_cheap",
    "presence.generate_model": "model.chat_strong",
    "presence.max_segments_group": "2",
    "presence.max_segments_dm": "4",
    "presence.tone": "warm_low_variance",
    "presence.recent_window": "12",
    "personas.butler_auto_provision": "true",
    "personas.max_extra_owned": "1",
}


def seed_settings(session: Session) -> None:
    for key, value in DEFAULT_MODEL_SETTINGS.items():
        existing = session.get(Setting, key)
        if not existing:
            session.add(Setting(key=key, value=value))
    migration_key = "memory.backend.sqlite_default_migrated"
    migration = session.get(Setting, migration_key)
    backend = session.get(Setting, "memory.backend")
    if not migration:
        if backend and backend.value == "mem0":
            backend.value = "sqlite"
            session.add(backend)
        session.add(Setting(key=migration_key, value="true"))
    vision_migration_key = "model.vision.glm_default_migrated"
    vision_migration = session.get(Setting, vision_migration_key)
    vision = session.get(Setting, "model.vision")
    if not vision_migration:
        if vision and vision.value == "openai/qwen3.5-27b":
            vision.value = "openai/glm-5.1"
            session.add(vision)
        session.add(Setting(key=vision_migration_key, value="true"))
    session.commit()


def get_setting(session: Session, key: str, default: Optional[str] = None) -> Optional[str]:
    row = session.get(Setting, key)
    return row.value if row else default


def set_setting(session: Session, key: str, value: str) -> Setting:
    row = session.get(Setting, key)
    if not row:
        row = Setting(key=key, value=value)
    else:
        row.value = value
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_settings(session: Session) -> list[Setting]:
    return session.exec(select(Setting).order_by(Setting.key)).all()


def resolve_model(session: Session, model_role: str, override: Optional[str] = None) -> Optional[str]:
    if override:
        return override
    return get_setting(session, f"model.{model_role}")
