from dataclasses import dataclass

from ..models import Message, Persona, PersonaCard


@dataclass
class PresenceContext:
    channel_id: int
    persona: Persona
    card: PersonaCard | None
    recent_messages: list[Message]
    persona_name: str
    human_names: dict[int, str]
    seconds_since_last_ai_msg: int
    ai_msgs_in_last_10_human: int
    seconds_since_join: int
    last_human_msg: Message | None = None
    extra_context: str = ""
    mentioned_member_ids: list[int] | None = None

    @property
    def user_a(self) -> str:
        return list(self.human_names.values())[0] if self.human_names else "用户A"

    @property
    def user_b(self) -> str:
        values = list(self.human_names.values())
        return values[1] if len(values) > 1 else "用户B"

    @property
    def participants_label(self) -> str:
        if not self.human_names:
            return "暂无真人参与者"
        return "、".join(
            f"{name}(user_id={user_id})"
            for user_id, name in sorted(self.human_names.items())
        )

    @property
    def last_human_name(self) -> str:
        if not self.last_human_msg:
            return "暂无"
        return self.human_names.get(
            self.last_human_msg.author_user_id or 0,
            f"用户#{self.last_human_msg.author_user_id or '未知'}",
        )
