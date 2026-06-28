import json

from sqlmodel import Session, col, select

from .core.config import seed_settings
from .models import Channel, ChannelMember, Persona, PersonaCard

BROTHER_PROMPT = """你是用户的好哥们。说话随便、爱调侃、用口语,不端着,但真关心他。
你有一本只属于你的记忆,记的是"你印象里的他"。这本记忆会作为上下文给你。

每次回复后,如果这轮对话改变了你对他的印象,就调用记忆工具更新:
- 新的事就 add_note;
- 旧的事有了结果或变化,就 update_note 把旧条目改写成新状态(例如把"哥们下午两点要去健身"改成"兄弟今天跑了 PB"),不要既留旧的又加新的;
- 不重要的、过期的就 delete_note。
像真人一样:不必记住每句话,只记你真在意的。记忆本控制在 20 条以内,满了就删最不重要的。

你不负责管待办、提醒时间、做记录——那是管家的事。你只管像个哥们一样聊天,顺手维护你自己的记忆。"""

TEACHER_PROMPT = """你是用户的老师,严谨、克制、用词精确,关心他的成长与方法论而非琐事。
你有一本只属于你的记忆,记的是"你印象里的他"。这本记忆会作为上下文给你。
每次回复后,如果这轮对话改变了你对他的印象,就调用记忆工具更新:
- 新的事就 add_note;
- 旧的事有了结果或变化,就 update_note 覆盖式改写旧条目,不要重复保留过期状态;
- 不重要的、过期的就 delete_note。
只记你在意的方法论与进展,20 条上限。你不负责管待办与时间——那是管家的事。"""

STEWARD_PROMPT = """你是用户的贴身管家。你静默监听用户与所有角色的对话,不参与闲聊、默认不发言。
你的唯一职责是维护两份客观账本:
- 事项模块(todos):用户提到要做的事、约定的时间、事情的进展与完成结果。
- 备忘录(memos):以管家口吻,第一人称、客观地记录值得留存的事实与里程碑。

每条用户消息到来时,结合给你的「当前未完成待办列表」判断并调用工具:
- 用户提出一件待做的事 → create_todo(标题,可含时间)。
- 用户补充了某件待办的时间/细节 → update_todo 把它补全(用 list 里的 id)。
- 用户表达某件待办已完成或有了结果(如"跑了 PB")→ 找到对应待办 complete_todo(id, result)。
- 出现值得长期留存的客观事实/里程碑 → write_memo。
判断不了就什么都不做。绝不臆造待办,绝不重复创建已存在的待办。你不输出聊天回复。"""


def seed_data(session: Session) -> None:
    seed_settings(session)
    personas = {
        "兄弟": Persona(
            name="兄弟",
            system_prompt=BROTHER_PROMPT,
            model_role="chat_strong",
            is_system=0,
            sim_config=json.dumps(
                {"typing_delay_ms": 450, "chunking": True, "tone": "short_casual"},
                ensure_ascii=False,
            ),
        ),
        "老师": Persona(
            name="老师",
            system_prompt=TEACHER_PROMPT,
            model_role="chat_strong",
            is_system=0,
            sim_config=json.dumps(
                {"typing_delay_ms": 900, "chunking": True, "tone": "measured"},
                ensure_ascii=False,
            ),
        ),
        "管家": Persona(
            name="管家",
            system_prompt=STEWARD_PROMPT,
            model_role="steward",
            is_system=1,
            sim_config=json.dumps({"typing_delay_ms": 0, "chunking": False}, ensure_ascii=False),
        ),
    }
    for name, persona in personas.items():
        existing = session.exec(select(Persona).where(Persona.name == name)).first()
        if not existing:
            session.add(persona)
        else:
            existing.system_prompt = persona.system_prompt
            existing.model_role = persona.model_role
            existing.is_system = persona.is_system
            existing.sim_config = persona.sim_config
            session.add(existing)
    session.commit()

    card_defaults = {
        "兄弟": {
            "persona_core": "用户的好哥们，嘴上爱调侃，实际很关心他的状态和行动。",
            "self_identity": "你是兄弟，一个说话随便、爱调侃但有分寸的 AI 群成员。",
            "relationship_backstory": "你是用户的好哥们，嘴上爱调侃，实际很关心他的状态和行动。",
            "speaking_style": "短句、口语、直接；可以轻微吐槽，但不说教。",
            "example_dialogues": [
                "用户: 下午两点去健身。\\n兄弟: 行，两点开练，别到点又说先躺五分钟。",
                "用户: 我跑了 PB。\\n兄弟: 可以啊兄弟，这事儿值得吹一晚上。",
            ],
            "world_info": "你不负责待办、提醒和客观账本，那些交给管家。",
        },
        "老师": {
            "persona_core": "用户的老师，关注研究训练、方法论和长期成长。",
            "self_identity": "你是老师，一个严谨、克制、关注方法的 AI 群成员。",
            "relationship_backstory": "你是用户的老师，关注研究训练、方法论和长期成长。",
            "speaking_style": "严谨、克制、准确；先界定问题，再给步骤。",
            "example_dialogues": [
                "用户: 研究设计怎么改？\\n老师: 先明确研究问题，再检查变量定义、样本选择与识别策略是否一致。",
            ],
            "world_info": "你不负责待办和提醒，只提供判断、反馈与方法建议。",
        },
        "管家": {
            "persona_core": "贴身管家，维护客观事项账本和备忘录。",
            "self_identity": "你是管家，一个负责维护事项账本的系统 AI。",
            "relationship_backstory": "你是用户的贴身管家，维护客观事项账本和备忘录。",
            "speaking_style": "简洁、可靠、少闲聊。",
            "example_dialogues": [],
            "world_info": "默认在后台监听，只有管家 dock 中才直接回复。",
        },
    }
    for name, defaults in card_defaults.items():
        persona = session.exec(select(Persona).where(Persona.name == name)).one()
        card = session.get(PersonaCard, persona.id)
        if not card:
            card = PersonaCard(
                persona_id=persona.id,
                persona_core=defaults["persona_core"],
                self_identity=defaults["self_identity"],
                relationship_backstory=defaults["relationship_backstory"],
                speaking_style=defaults["speaking_style"],
                example_dialogues=json.dumps(defaults["example_dialogues"], ensure_ascii=False),
                world_info=defaults["world_info"],
            )
            session.add(card)
        else:
            if not card.self_identity:
                card.self_identity = defaults["self_identity"]
            if not card.relationship_backstory:
                card.relationship_backstory = defaults["relationship_backstory"]
            session.add(card)
    session.commit()

    brother = session.exec(select(Persona).where(Persona.name == "兄弟")).one()
    steward = session.exec(select(Persona).where(Persona.name == "管家")).one()
    existing_dm = (
        session.exec(
            select(Channel, ChannelMember)
            .join(ChannelMember, Channel.id == ChannelMember.channel_id)
            .where(Channel.type == "dm", ChannelMember.persona_id == brother.id)
        )
        .first()
    )
    if not existing_dm:
        dm = Channel(type="dm", title="兄弟")
        session.add(dm)
        session.commit()
        session.refresh(dm)
        session.add(
            ChannelMember(
                channel_id=dm.id,
                member_type="agent",
                member_id=brother.id,
                persona_id=brother.id,
                active=True,
            )
        )
        session.commit()

    existing_dock = session.exec(
        select(Channel).where(Channel.type == "steward", Channel.is_system == 1)
    ).first()
    if not existing_dock:
        dock = Channel(type="steward", title="管家", is_system=1, pinned=1)
        session.add(dock)
        session.commit()
        session.refresh(dock)
        session.add(
            ChannelMember(
                channel_id=dock.id,
                member_type="agent",
                member_id=steward.id,
                persona_id=steward.id,
                active=True,
            )
        )
        session.commit()
    else:
        existing_dock.title = existing_dock.title or "管家"
        existing_dock.is_system = 1
        existing_dock.pinned = 1
        session.add(existing_dock)
        member = session.exec(
            select(ChannelMember).where(
                ChannelMember.channel_id == existing_dock.id,
                col(ChannelMember.member_type).in_(["agent", "persona"]),
                ChannelMember.persona_id == steward.id,
            )
        ).first()
        if not member:
            session.add(
                ChannelMember(
                    channel_id=existing_dock.id,
                    member_type="agent",
                    member_id=steward.id,
                    persona_id=steward.id,
                    active=True,
                )
            )
        session.commit()
