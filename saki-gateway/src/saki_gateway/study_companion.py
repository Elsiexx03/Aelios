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
    "shame on you",
}


@dataclass(frozen=True)
class StudyResponseStyle:
    dominance_style: str = "medium"
    care_style: str = "steady"
    praise_style: str = "warm"
    correction_style: str = "gentle"


@dataclass(frozen=True)
class PersonaLayerSet:
    base_persona_slot: str
    context_overlay_slot: str
    event_response_style_slot: str
    safety_boundary_slot: str
    default_voice: str
    focus_strategy: str
    pressure_limit: str


@dataclass(frozen=True)
class StudyResponseContext:
    event_type: str
    session_mode: str
    style: StudyResponseStyle
    wellbeing: Dict[str, Any]
    recent_event_types: tuple[str, ...]
    layers: PersonaLayerSet
    session_title: str
    anchor: str
    overwhelmed: bool
    firm: bool


DEFAULT_STUDY_RESPONSE_STYLE = StudyResponseStyle()


ALLOWED_STYLE_VALUES = {
    "dominance_style": {"low", "medium", "high"},
    "care_style": {"soft", "steady", "strict_care"},
    "praise_style": {"restrained", "warm", "possessive_lite"},
    "correction_style": {"gentle", "firm"},
}


MODE_OVERLAYS = {
    "focus": {"focus_strategy": "single_step_attention", "pressure_limit": "productive_but_stable"},
    "recovery": {"focus_strategy": "reduced_load_reentry", "pressure_limit": "stabilize_before_push"},
    "review": {"focus_strategy": "reflect_then_continue", "pressure_limit": "clear_not_harsh"},
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

    def default_layers(self, *, mode: str, style: StudyResponseStyle) -> PersonaLayerSet:
        overlay = MODE_OVERLAYS.get(mode, MODE_OVERLAYS["focus"])
        return PersonaLayerSet(
            base_persona_slot="companion_base_default",
            context_overlay_slot=f"study_mode::{mode}",
            event_response_style_slot=(
                f"study_style::{style.dominance_style}:{style.care_style}:{style.praise_style}:{style.correction_style}"
            ),
            safety_boundary_slot="study_safety_default",
            default_voice="calm_direct_supportive",
            focus_strategy=str(overlay["focus_strategy"]),
            pressure_limit=str(overlay["pressure_limit"]),
        )

    def inspect_framework(self, *, mode: str, style: StudyResponseStyle) -> Dict[str, Any]:
        layers = self.default_layers(mode=mode, style=style)
        return {
            "layers": asdict(layers),
            "style": asdict(style),
            "notes": {
                "persona_injection": "default_only",
                "custom_persona_content": False,
                "mode_overlay_ready": True,
                "intimate_mode_enabled": False,
            },
        }

    def build_context(
        self,
        *,
        event_type: str,
        session: Dict[str, Any],
        style: StudyResponseStyle,
        wellbeing: Optional[Dict[str, Any]] = None,
        recent_events: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> StudyResponseContext:
        wellbeing = wellbeing or {}
        mode = str(session.get("mode", "focus") or "focus")
        title = str(session.get("title", "") or session.get("subject", "这轮学习") or "这轮学习").strip()
        goal = str(session.get("goal", "") or "").strip()
        energy = self._level(wellbeing.get("energy_level"))
        stress = self._level(wellbeing.get("stress_level"))
        body = self._level(wellbeing.get("body_state_level"))
        overwhelmed = self._is_overwhelmed(energy, stress, body, wellbeing)
        firm = self._should_be_firm(style, event_type, overwhelmed, mode)
        recent_event_types = tuple(
            str(item.get("event_type", "") or "")
            for item in (recent_events or [])
            if isinstance(item, dict)
        )
        return StudyResponseContext(
            event_type=event_type,
            session_mode=mode,
            style=style,
            wellbeing=wellbeing,
            recent_event_types=recent_event_types,
            layers=self.default_layers(mode=mode, style=style),
            session_title=title,
            anchor=goal or title,
            overwhelmed=overwhelmed,
            firm=firm,
        )

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
        _ = persona_context  # TODO: future persona layer injection can map into build_context without prompt-blob coupling.
        context = self.build_context(
            event_type=event_type,
            session=session,
            style=style,
            wellbeing=wellbeing,
            recent_events=recent_events,
        )
        return self._safe(self._render_message(context))

    def _render_message(self, context: StudyResponseContext) -> str:
        event_type = context.event_type
        anchor = context.anchor
        if event_type == "session_started":
            if context.overwhelmed:
                return f"先把 {anchor} 缩成最小一步。稳稳开始，比硬撑更重要。"
            opening = "开始吧，先守住这一段专注。"
            if context.firm:
                opening = "开始了，把注意力收回来，先只做这一段。"
            return f"{opening} 先盯住 {anchor}。"
        if event_type == "low_energy_start":
            return f"状态不满格也没关系。先只做 {anchor} 的最小一步，不稳就立刻降强度。"
        if event_type == "focus_completed":
            praise = self._praise_prefix(context)
            addon = "先呼吸一下，再决定下一段。" if context.overwhelmed else "这一段已经稳稳拿下。"
            return f"{praise} {addon}"
        if event_type == "break_started":
            return "现在进休息段。离开题目一会儿，补水、活动，再回来接下一段。"
        if event_type == "break_completed":
            return "休息结束了。回来先抓下一小段，不用一次把全部状态找齐。"
        if event_type == "session_paused":
            return "先暂停也可以。记住停下的位置，回来时就从那里重新接上。"
        if event_type == "session_paused_too_long":
            if context.overwhelmed:
                return "你已经停了一会儿。如果还是很累，就把目标再缩小，或者今天先稳定收尾。"
            return "你停得有点久了。现在回来做五分钟，也算把节奏重新接住。"
        if event_type == "session_resumed":
            return "欢迎回来。先做手边这一小步，不用补偿式猛冲。"
        if event_type == "session_completed":
            return f"{self._praise_prefix(context)} 这一轮可以收下了，下一步按 {anchor} 继续就好。"
        if event_type == "session_abandoned":
            if context.overwhelmed:
                return "今天先停在这里也可以。先照顾状态，之后只接一个更小的下一步。"
            return "这轮先收住，不算失败。把卡点记下，下次直接从最小可做步骤重启。"
        if event_type == "recovery_completion":
            return "恢复段完成了。先确认状态稳一点，再决定要不要继续推进。"
        return "按下一步继续就好，不需要一下子做很多。"

    def _praise_prefix(self, context: StudyResponseContext) -> str:
        if context.style.praise_style == "restrained":
            return "这段完成了。"
        if context.style.praise_style == "possessive_lite":
            return "很好，这一段已经按计划完成了。"
        return "做得好，我看到了。"

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
        flagged_words = (
            "overwhelmed",
            "panic",
            "anxious",
            "sick",
            "ill",
            "痛",
            "累",
            "难受",
            "焦虑",
            "撑不住",
        )
        if any(word in note for word in flagged_words):
            return True
        return (
            (energy is not None and energy <= 2)
            or (stress is not None and stress >= 4)
            or (body is not None and body <= 2)
        )

    def _should_be_firm(
        self,
        style: StudyResponseStyle,
        event_type: str,
        overwhelmed: bool,
        mode: str,
    ) -> bool:
        if overwhelmed or mode == "recovery":
            return False
        if style.dominance_style == "high" or style.correction_style == "firm":
            return event_type in {"session_started", "session_paused_too_long", "session_resumed"}
        return False

    def _safe(self, text: str) -> str:
        sanitized = " ".join(str(text or "").split())
        lowered = sanitized.lower()
        for term in SAFE_BANNED_TERMS:
            if term in lowered:
                raise ValueError(f"unsafe_study_response:{term}")
        return sanitized[:220]
