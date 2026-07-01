import json
from typing import Optional

from sqlmodel import Session

from ..core.llm import counted_completion, provider_ready
from ..models import Channel
from ..chat.context_assembler import assemble_group_presence_context
from .context import PresenceContext
from .triggers import ConsiderResult, _model_from_setting, should_consider


class InterjectionPolicy:
    def __init__(self, session: Session, cfg: dict[str, str]):
        self.session = session
        self.cfg = cfg

    def should_consider(self, ctx: PresenceContext) -> ConsiderResult:
        return should_consider(ctx, self.cfg, self.session)

    def generate_reply(self, ctx: PresenceContext) -> Optional[list[str]]:
        model = _model_from_setting(self.session, self.cfg.get("presence.generate_model"), "model.chat_strong")
        identity_reply = self._identity_reply(ctx)
        if identity_reply:
            return [identity_reply]
        if not provider_ready(model):
            return self._fallback_reply(ctx)
        tone = self._tone_instruction()
        channel = self.session.get(Channel, ctx.channel_id)
        if not channel:
            return None
        assembled = assemble_group_presence_context(
            self.session,
            channel,
            ctx.persona,
            ctx.recent_messages,
            self.cfg,
            ctx.mentioned_member_ids or [],
        )
        facts_section = ""
        if _enabled(self.cfg.get("memory.public_facts.enabled")):
            facts_section = f"""
频道长期事实：
{assembled.long_term_facts or "（无可用事实）"}
"""
        system = f"""你是 {ctx.persona_name}，正在一个多人频道旁边。
{assembled.roster}
刚刚发言的人是：{ctx.last_human_name}。
你不是这场对话的主角，他们俩才是。多数时候保持安静。
只有当你能加一句让【两个人都】更好接话、或一起会心一笑的话时才开口。
默认只发 1 条；确实自然时可以 2 条。直接输出 JSON 字符串数组，每个元素是一条独立聊天气泡。
只输出你自己的聊天正文，不要输出“姓名(真人|AI,...):”这类署名前缀，不要复述【最近对话】原文。
不要总结、不要复述、不要把话题拽到自己身上。
如果此刻没有真正值得说的，只回复：<SILENCE>

系统规则：
{assembled.system_rules}

角色身份：
{assembled.persona_identity}

语气：
{assembled.persona_voice}
{tone}
{facts_section}

滚动摘要：
{assembled.rolling_summary or "（空）"}

检索片段：
{assembled.retrieved_snippets or "（空）"}

最近对话：
{assembled.recent_messages}
"""
        try:
            response = counted_completion(
                model=model,
                messages=[{"role": "system", "content": system}],
                max_tokens=180,
            )
            text = (response.choices[0].message.content or "").strip()
        except Exception:
            return None
        if not text or "<SILENCE>" in text:
            return None
        return _segments(text)[:2] or None

    def _fallback_reply(self, ctx: PresenceContext) -> Optional[list[str]]:
        if ctx.mentioned_member_ids:
            return [self._identity_reply(ctx) or "我在。你们继续聊，我只在真有必要时插一句。"]
        return None

    def _identity_reply(self, ctx: PresenceContext) -> Optional[str]:
        if not ctx.last_human_msg:
            return None
        text = ctx.last_human_msg.content.strip()
        identity_patterns = [
            "我是谁",
            "你能分清",
            "分清我们",
            "分得清",
            "谁是谁",
            "我叫什么",
        ]
        if not any(pattern in text for pattern in identity_patterns):
            return None
        names = "、".join(ctx.human_names.values()) or "暂时没有识别到真人名字"
        return f"能分清。这个频道里的真人有：{names}。刚刚说话的是 {ctx.last_human_name}。"

    def _tone_instruction(self) -> str:
        tone = self.cfg.get("presence.tone") or "warm_low_variance"
        if tone == "sheldon_high_variance":
            return "可以更尖锐、更有梗，但仍然只能短插一句。"
        return "温和、低打扰、像旁边的熟人轻轻补一句。"


def _enabled(raw: str | None) -> bool:
    return str(raw or "").lower() in {"1", "true", "yes", "on"}


def _segments(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, list):
        return [str(item).strip()[:240] for item in value if str(item).strip()]
    return [part.strip()[:240] for part in raw.split("\n\n") if part.strip()] or [raw.strip()[:240]]
