from typing import Optional

from litellm import completion
from sqlmodel import Session

from ..core.llm import provider_ready
from .context import PresenceContext
from .triggers import ConsiderResult, _model_from_setting, format_recent_messages, should_consider


class InterjectionPolicy:
    def __init__(self, session: Session, cfg: dict[str, str]):
        self.session = session
        self.cfg = cfg

    def should_consider(self, ctx: PresenceContext) -> ConsiderResult:
        return should_consider(ctx, self.cfg, self.session)

    def generate_reply(self, ctx: PresenceContext) -> Optional[str]:
        model = _model_from_setting(self.session, self.cfg.get("presence.generate_model"), "model.chat_strong")
        if not provider_ready(model):
            return self._fallback_reply(ctx)
        tone = self._tone_instruction()
        card = ctx.card
        persona_core = card.persona_core if card and card.persona_core else ctx.persona.system_prompt
        system = f"""你是 {ctx.persona_name}，正在 {ctx.user_a} 和 {ctx.user_b} 的对话旁边。
你不是这场对话的主角，他们俩才是。多数时候保持安静。
只有当你能加一句让【两个人都】更好接话、或一起会心一笑的话时才开口。
开口就一两句，短。不要总结、不要复述、不要把话题拽到自己身上。
如果此刻没有真正值得说的，只回复：<SILENCE>

角色设定：
{persona_core}

语气：
{tone}

最近对话：
{format_recent_messages(ctx)}
"""
        try:
            response = completion(
                model=model,
                messages=[{"role": "system", "content": system}],
                max_tokens=180,
            )
            text = (response.choices[0].message.content or "").strip()
        except Exception:
            return None
        if not text or "<SILENCE>" in text:
            return None
        return text[:240]

    def _fallback_reply(self, ctx: PresenceContext) -> Optional[str]:
        if ctx.last_mentions_ai or ctx.last_names_ai:
            return "我在。你们继续，我只插一句：这事儿可以先按最小可行动作往前推。"
        return None

    def _tone_instruction(self) -> str:
        tone = self.cfg.get("presence.tone") or "warm_low_variance"
        if tone == "sheldon_high_variance":
            return "可以更尖锐、更有梗，但仍然只能短插一句。"
        return "温和、低打扰、像旁边的熟人轻轻补一句。"

