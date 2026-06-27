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

    @property
    def user_a(self) -> str:
        return list(self.human_names.values())[0] if self.human_names else "用户A"

    @property
    def user_b(self) -> str:
        values = list(self.human_names.values())
        return values[1] if len(values) > 1 else "用户B"

    @property
    def last_mentions_ai(self) -> bool:
        if not self.last_human_msg:
            return False
        text = self.last_human_msg.content
        return f"@{self.persona_name}" in text or "@AI" in text

    @property
    def last_names_ai(self) -> bool:
        if not self.last_human_msg:
            return False
        text = self.last_human_msg.content
        return self.persona_name in text

