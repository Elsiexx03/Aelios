from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Optional


SAFE_BANNED_TERMS = {
    "pathetic",
    "lazy pig",
    "useless",
    "disgusting",
    "worthless",
    "punish",
    "punishment",
    "humiliate",
    "humiliating",
    "slut",
    "idiot",
    "stupid",
}

SAFE_EXPLICIT_TERMS = {
    "fuck",
    "性爱",
    "sexual",
    "erotic",
    "色情",
    "调教",
}


@dataclass(frozen=True)
class StudyResponseStyle:
    dominance_style: str = "medium"
    care_style: str = "steady"
    praise_style: str = "warm"
    correction_style: str = "gentle"


@dataclass(frozen=True)
class LayeredPersonaSlots:
    base_persona_slot: str = "neutral_companion"
    context_overlay_slot: str = "study_focus"
    event_response_style_slot: str = "brief_supportive"
    safety_boundary_slot: str = "study_safe_boundaries"


@dataclass(frozen=True)
class ResponseGenerationPlan:
    message: str
    debug: Dict[str, Any]


DEFAULT_STUDY_RESPONSE_STYLE = StudyResponseStyle()
DEFAULT_LAYERED_PERSONA_SLOTS = LayeredPersonaSlots()


ALLOWED_STYLE_VALUES = {
    "dominance_style": {"low", "medium", "high"},
    "care_style": {"soft", "steady", "strict_care"},
    "praise_style": {"restrained", "warm", "possessive_lite"},
    "correction_style": {"gentle", "firm"},
}


class StudyCompanionResponder:
    def normalize_style(self, payload: Optional[Dict[str, Any]]) -> StudyResponseStyle:
        base = asdict(DEFAULT_STUDY_RESPONSE_STYLE)
        if isinstance(payload, dict):
            for key, allowed in ALLOWED_STYLE_VALUES.items():
                value = str(payload.get(key, "") or "").strip().lower()
                if value in allowed:
                    base[key] = value
        return StudyResponseStyle(**base)

    def describe_framework(
        self,
        *,
        session: Optional[Dict[str, Any]] = None,
        style: Optional[StudyResponseStyle] = None,
        wellbeing: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        session = session or {}
        wellbeing = wellbeing or {}
        normalized_style = style or DEFAULT_STUDY_RESPONSE_STYLE
        mode = str(session.get("mode", "focus") or "focus")
        energy = self._level(wellbeing.get("energy_level"))
        stress = self._level(wellbeing.get("stress_level"))
        body = self._level(wellbeing.get("body_state_level"))
        overwhelmed = self._is_overwhelmed(energy, stress, body, wellbeing)
        layer_slots = DEFAULT_LAYERED_PERSONA_SLOTS
        return {
            "layered_persona": asdict(layer_slots),
            "mode_overlay": {
                "focus": "study_focus",
                "recovery": "study_recovery",
                "review": "study_review",
            }.get(mode, "study_focus"),
            "style": asdict(normalized_style),
            "wellbeing_signal": {
                "energy_level": energy,
                "stress_level": stress,
                "body_state_level": body,
                "overwhelmed": overwhelmed,
            },
            "safety": {
                "explicit_language_allowed": False,
                "degrading_language_allowed": False,
                "intimate_or_rp_allowed": False,
                "prefer_smaller_steps_when_overwhelmed": True,
            },
            "todo": "Future persona injection should fill the layer slots without replacing the event framework.",
        }

    def build_response_plan(
        self,
        *,
        event_type: str,
        session: Dict[str, Any],
        style: StudyResponseStyle,
        wellbeing: Optional[Dict[str, Any]] = None,
        recent_events: Optional[Iterable[Dict[str, Any]]] = None,
        persona_context: str = "",
    ) -> ResponseGenerationPlan:
        wellbeing = wellbeing or {}
        recent_events = list(recent_events or [])
        title = str(session.get("title", "") or "").strip()
        goal = str(session.get("goal", "") or "").strip()
        subject = title or session.get("subject") or "这轮学习"
        anchor = goal or subject
        mode = str(session.get("mode", "focus") or "focus")
        energy = self._level(wellbeing.get("energy_level"))
        stress = self._level(wellbeing.get("stress_level"))
        body = self._level(wellbeing.get("body_state_level"))
        overwhelmed = self._is_overwhelmed(energy, stress, body, wellbeing)
        firm = self._should_be_firm(style, event_type, overwhelmed)
        context = self.describe_framework(session=session, style=style, wellbeing=wellbeing)
        context["persona_context"] = str(persona_context or "").strip()
        context["recent_event_types"] = [str(item.get("event_type", "") or "") for item in recent_events[:5]]
        context["event_type"] = event_type
        context["anchor"] = anchor
        context["session_mode"] = mode
        message = self._build_message_text(
            event_type=event_type,
            mode=mode,
            anchor=anchor,
            style=style,
            overwhelmed=overwhelmed,
            firm=firm,
        )
        return ResponseGenerationPlan(message=self._safe(message), debug=context)

    def build_message(
        self,
        *,
        event_type: str,
        session: Dict[str, Any],
        style: StudyResponseStyle,
        wellbeing: Optional[Dict[str, Any]] = None,
        recent_events: Optional[Iterable[Dict[str, Any]]] = None,
        persona_context: str = "",
    ) -> str:
        return self.build_response_plan(
            event_type=event_type,
            session=session,
            style=style,
            wellbeing=wellbeing,
            recent_events=recent_events,
            persona_context=persona_context,
        ).message

    def _build_message_text(
        self,
        *,
        event_type: str,
        mode: str,
        anchor: str,
        style: StudyResponseStyle,
        overwhelmed: bool,
        firm: bool,
    ) -> str:
        if event_type == "session_started":
            if overwhelmed:
                return f"先别急，我们把目标缩成 {anchor} 的最小一步，稳稳开始就够了。"
            if mode == "review":
                return f"开始吧，先把复盘范围压小，只盯住 {anchor}。"
            opening = "开始吧，我陪你把这段专注守住。" if not firm else "开始了，先把注意力收回来，我们只做眼前这一段。"
            return f"{opening} 先盯住 {anchor}。"
        if event_type == "low_energy_start":
            return "我知道你现在状态不满格。先做最小的一步，撑不住就告诉我，我们立刻降强度。"
        if event_type == "focus_completed":
            praise = {
                "restrained": "这段完成了。",
                "warm": "做得好，我看到了。",
                "possessive_lite": "很好，这一段你有稳稳跟上。",
            }.get(style.praise_style, "做得好，我看到了。")
            addon = " 先呼吸一下，再决定要不要继续。" if overwhelmed else " 这一段你是稳住了的。"
            return f"{praise}{addon}"
        if event_type == "break_started":
            if mode == "recovery":
                return "现在进恢复段。先离开题目一会儿，喝水、活动肩颈，等稳一点我们再接。"
            return "现在进休息段。离开题目一会儿，喝水、活动肩颈，等下我们再接上。"
        if event_type == "break_completed":
            if mode == "review":
                return "休息够了，回来只看下一处关键点，不需要一次复盘完全部内容。"
            return "休息够了，回来就只抓下一小段，不需要一下子把全部状态找齐。"
        if event_type == "session_paused":
            return "先暂停也可以。把这次停下的原因记住，等你回来我帮你重新接住节奏。"
        if event_type == "session_paused_too_long":
            if overwhelmed:
                return "你已经停了有一会儿。如果还是很累，我们就把目标再缩小，或者今天先体面收尾。"
            if firm:
                return "你停得有点久了。现在回来做五分钟也算重启，不要继续往后拖。"
            return "你已经停了一阵。现在回来做一小步就够，我们先把节奏接回去。"
        if event_type == "session_resumed":
            if mode == "recovery":
                return "欢迎回来。别补偿式猛冲，先做最轻的一步，把状态慢慢接回来。"
            return "欢迎回来。别补偿式猛冲，先把手上的下一步做完。"
        if event_type == "session_completed":
            praise = "完成了。"
            if style.praise_style == "warm":
                praise = "很好，我为你高兴。"
            elif style.praise_style == "possessive_lite":
                praise = "很好，这段你乖乖做完了。"
            return f"{praise} 这一轮可以收下了，记得按 {anchor} 的方向接上下一步。"
        if event_type == "session_abandoned":
            if overwhelmed:
                return "今天先停在这里也没关系。先照顾状态，我们之后只接一个更小的下一步。"
            return "这轮先收住，不算失败。把卡点留给我，我们下一次直接从最小可做步骤重新开始。"
        if event_type == "recovery_completion":
            return "恢复段完成了，这就很重要。先确认你稳一点了，再决定要不要继续推进。"
        return "我在。我们按下一步继续，不急着一下子做很多。"

    def _level(self, value: Any) -> Optional[int]:
        if value in {None, ""}:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _is_overwhelmed(
        self,
        energy: Optional[int],
        stress: Optional[int],
        body: Optional[int],
        wellbeing: Dict[str, Any],
    ) -> bool:
        note = str(wellbeing.get("note", "") or "").lower()
        flagged_words = ("overwhelmed", "panic", "anxious", "sick", "ill", "痛", "累", "难受", "焦虑", "撑不住")
        if any(word in note for word in flagged_words):
            return True
        return (energy is not None and energy <= 2) or (stress is not None and stress >= 4) or (body is not None and body <= 2)

    def _should_be_firm(self, style: StudyResponseStyle, event_type: str, overwhelmed: bool) -> bool:
        if overwhelmed:
            return False
        if style.dominance_style == "high" or style.correction_style == "firm":
            return event_type in {"session_started", "session_paused_too_long", "session_resumed"}
        return False

    def _safe(self, text: str) -> str:
        sanitized = " ".join(str(text or "").split())
        lowered = sanitized.lower()
        for term in SAFE_BANNED_TERMS | SAFE_EXPLICIT_TERMS:
            if term in lowered:
                raise ValueError(f"unsafe_study_response:{term}")
        return sanitized[:220]
