from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ..models import Message, Persona

LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def _bucket(hour: int) -> str:
    if 5 <= hour < 8:
        return "清晨"
    if 8 <= hour < 11:
        return "上午"
    if 11 <= hour < 14:
        return "午间"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 21:
        return "傍晚"
    if 21 <= hour < 24:
        return "夜间"
    return "深夜"


def _ago(iso_value: str | None, now: datetime) -> str:
    if not iso_value:
        return "无记录"
    try:
        past = datetime.fromisoformat(iso_value)
    except ValueError:
        return "未知"
    if past.tzinfo is None:
        past = past.replace(tzinfo=timezone.utc)
    delta = now - past.astimezone(now.tzinfo)
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return f"{seconds} 秒前"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} 分钟前"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} 小时前"
    days = hours // 24
    return f"{days} 天前"


def build_time_context(
    recent: list[Message],
    persona: Persona | None = None,
) -> str:
    now = datetime.now(LOCAL_TZ)
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    prior_messages = recent[:-1] if recent else []
    last_channel_message = prior_messages[-1] if prior_messages else None
    persona_messages = [
        message
        for message in prior_messages
        if persona and message.sender == "persona" and message.persona_id == persona.id
    ]
    last_persona_message = persona_messages[-1] if persona_messages else None
    persona_label = persona.name if persona else "当前 agent"
    return "\n".join(
        [
            "时间上下文:",
            f"- 当前本地时间: {now.strftime('%Y-%m-%d %H:%M:%S')} ({weekdays[now.weekday()]})",
            f"- 当前时段: {_bucket(now.hour)}",
            f"- 距本频道上一条消息: {_ago(last_channel_message.created_at if last_channel_message else None, now)}",
            f"- {persona_label} 距上次发言: {_ago(last_persona_message.created_at if last_persona_message else None, now)}",
        ]
    )
