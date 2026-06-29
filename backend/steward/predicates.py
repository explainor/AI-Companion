"""
受控 predicate 词表。

update_behavior:
  "overwrite"  — 同 predicate 存在旧值时，写入新值并将旧值 supersedes_id 指向新 id。
  "state"      — 状态型，保留历史但不主动 supersede。
  "accumulate" — 累积型，永不 supersede，只新增。
"""

MEMORY_PREDICATES: dict[str, dict] = {
    "profile.name": {
        "label": "称呼/名字",
        "group": "基本信息",
        "update_behavior": "overwrite",
    },
    "profile.location": {
        "label": "所在城市",
        "group": "基本信息",
        "update_behavior": "overwrite",
    },
    "profile.occupation": {
        "label": "职业/身份",
        "group": "基本信息",
        "update_behavior": "overwrite",
    },
    "profile.life_stage": {
        "label": "当前人生阶段",
        "group": "基本信息",
        "update_behavior": "overwrite",
    },
    "pref.communication": {
        "label": "沟通风格偏好",
        "group": "偏好",
        "update_behavior": "overwrite",
    },
    "pref.schedule": {
        "label": "作息规律",
        "group": "偏好",
        "update_behavior": "overwrite",
    },
    "pref.topic_like": {
        "label": "感兴趣的话题",
        "group": "偏好",
        "update_behavior": "overwrite",
    },
    "pref.topic_avoid": {
        "label": "不想聊的话题",
        "group": "偏好",
        "update_behavior": "overwrite",
    },
    "pref.response_style": {
        "label": "回复风格偏好",
        "group": "偏好",
        "update_behavior": "overwrite",
    },
    "project.current": {
        "label": "当前主要项目",
        "group": "进行中的事",
        "update_behavior": "state",
    },
    "project.progress": {
        "label": "项目最新进度",
        "group": "进行中的事",
        "update_behavior": "state",
    },
    "goal.near": {
        "label": "近期目标",
        "group": "进行中的事",
        "update_behavior": "state",
    },
    "goal.far": {
        "label": "长期方向",
        "group": "进行中的事",
        "update_behavior": "state",
    },
    "mood.current": {
        "label": "最近状态/情绪",
        "group": "最近状态",
        "update_behavior": "state",
    },
    "relation.person": {
        "label": "重要的人",
        "group": "关系",
        "update_behavior": "accumulate",
    },
    "relation.dynamic": {
        "label": "关系动态",
        "group": "关系",
        "update_behavior": "accumulate",
    },
    "event.recent": {
        "label": "近期重要事件",
        "group": "近期",
        "update_behavior": "accumulate",
    },
    "event.concern": {
        "label": "当前担忧/压力源",
        "group": "近期",
        "update_behavior": "accumulate",
    },
}

PREDICATE_PROMPT_BLOCK = "\n".join(
    f"- {key}（{value['label']}）[{value['update_behavior']}]"
    for key, value in MEMORY_PREDICATES.items()
)

GROUP_ORDER = ["基本信息", "偏好", "进行中的事", "最近状态", "关系", "近期"]
