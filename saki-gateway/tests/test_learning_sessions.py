from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from saki_gateway.runtime_store import RuntimeStore
from saki_gateway.server import GatewayApp
from saki_gateway.study_companion import StudyCompanionResponder


class LearningSessionTests(unittest.TestCase):
    def _make_runtime_store(self) -> RuntimeStore:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base = Path(temp_dir.name)
        return RuntimeStore(base / "gateway.db", base / "events.jsonl")

    def _make_app(self) -> GatewayApp:
        app = GatewayApp.__new__(GatewayApp)
        app.runtime_store = self._make_runtime_store()
        app.memory_store = SimpleNamespace(upsert_memory=lambda **kwargs: None)
        app._refresh_active_memory = lambda: None
        app._events = []
        app._record_event = lambda event_type, payload, **kwargs: app._events.append((event_type, payload))
        app.study_responder = StudyCompanionResponder()
        return app

    def _start(self, app: GatewayApp, **overrides):
        body = {
            "title": "线代复习",
            "goal": "先做两道题",
            "subject": "线性代数",
            "mode": "focus",
            "planned_minutes": 15,
            "pomodoro_count": 1,
            "started_at": "2026-01-02T10:00:00",
        }
        body.update(overrides)
        return app.create_learning_session_payload(body)["item"]

    def test_creating_learning_session(self) -> None:
        app = self._make_app()
        item = self._start(app)
        self.assertEqual(item["status"], "active")
        self.assertEqual(item["planned_minutes"], 15)
        self.assertEqual(item["runtime_state"], "focus")
        events = app.list_learning_session_events_payload(item["id"])["items"]
        self.assertEqual(events[0]["event_type"], "session_started")

    def test_prevent_multiple_active_sessions(self) -> None:
        app = self._make_app()
        self._start(app)
        with self.assertRaises(ValueError):
            self._start(app, title="第二个会话")

    def test_update_active_session(self) -> None:
        app = self._make_app()
        item = self._start(app)
        updated = app.update_learning_session_payload(
            item["id"], {"planned_minutes": 5, "mode": "recovery", "goal": "低负担继续"}
        )["item"]
        self.assertEqual(updated["planned_minutes"], 5)
        self.assertEqual(updated["mode"], "recovery")

    def test_pause_and_resume_runtime_events(self) -> None:
        app = self._make_app()
        item = self._start(app)
        paused = app.update_learning_session_runtime_payload(
            item["id"],
            {"action": "pause", "timestamp": "2026-01-02T10:05:00", "elapsed_minutes": 5, "remaining_minutes": 10},
        )["item"]
        self.assertEqual(paused["runtime_state"], "paused")
        self.assertEqual(paused["resume_runtime_state"], "focus")
        resumed = app.update_learning_session_runtime_payload(
            item["id"],
            {"action": "resume", "timestamp": "2026-01-02T10:08:00", "elapsed_minutes": 5, "remaining_minutes": 10},
        )["item"]
        self.assertEqual(resumed["runtime_state"], "focus")
        events = app.list_learning_session_events_payload(item["id"])["items"]
        event_types = [event["event_type"] for event in events]
        self.assertIn("session_paused", event_types)
        self.assertIn("session_resumed", event_types)
        resumed_event = next(event for event in events if event["event_type"] == "session_resumed")
        self.assertEqual(resumed_event["payload"]["resumed_to"], "focus")


    def test_resume_restores_break_runtime_state(self) -> None:
        app = self._make_app()
        item = self._start(app)
        app.update_learning_session_runtime_payload(item["id"], {"action": "focus_completed", "elapsed_minutes": 15, "remaining_minutes": 0})
        on_break = app.update_learning_session_runtime_payload(item["id"], {"action": "break_started"})["item"]
        self.assertEqual(on_break["runtime_state"], "break")
        paused = app.update_learning_session_runtime_payload(item["id"], {"action": "pause", "timestamp": "2026-01-02T10:16:00"})["item"]
        self.assertEqual(paused["resume_runtime_state"], "break")
        resumed = app.update_learning_session_runtime_payload(item["id"], {"action": "resume", "timestamp": "2026-01-02T10:18:00"})["item"]
        self.assertEqual(resumed["runtime_state"], "break")

    def test_focus_and_break_events(self) -> None:
        app = self._make_app()
        item = self._start(app)
        completed = app.update_learning_session_runtime_payload(item["id"], {"action": "focus_completed", "elapsed_minutes": 15, "remaining_minutes": 0})["item"]
        self.assertEqual(completed["pomodoro_count"], 2)
        on_break = app.update_learning_session_runtime_payload(item["id"], {"action": "break_started", "elapsed_minutes": 15})["item"]
        self.assertEqual(on_break["runtime_state"], "break")
        self.assertEqual(on_break["remaining_minutes"], 5)
        back = app.update_learning_session_runtime_payload(item["id"], {"action": "break_completed", "elapsed_minutes": 15, "remaining_minutes": 5})["item"]
        self.assertEqual(back["runtime_state"], "focus")
        events = app.list_learning_session_events_payload(item["id"])["items"]
        event_types = [event["event_type"] for event in events]
        self.assertIn("focus_completed", event_types)
        self.assertIn("break_completed", event_types)
        break_event = next(event for event in events if event["event_type"] == "break_started")
        self.assertEqual(break_event["payload"]["break_kind"], "short")
        self.assertEqual(break_event["payload"]["break_minutes"], 5)


    def test_invalid_runtime_transition_rejected(self) -> None:
        app = self._make_app()
        item = self._start(app)
        with self.assertRaises(ValueError):
            app.update_learning_session_runtime_payload(item["id"], {"action": "break_started"})
        with self.assertRaises(ValueError):
            app.update_learning_session_runtime_payload(item["id"], {"action": "break_completed"})

    def test_complete_learning_session(self) -> None:
        app = self._make_app()
        item = self._start(app)
        completed = app.complete_learning_session_payload(
            item["id"],
            {
                "ended_at": "2026-01-02T10:27:00",
                "summary": "完成两道基础题",
                "blockers": "第二题计算慢",
                "next_step": "晚点复盘错题",
            },
        )["item"]
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["actual_minutes"], 27)

    def test_abandon_learning_session(self) -> None:
        app = self._make_app()
        item = self._start(app)
        abandoned = app.abandon_learning_session_payload(
            item["id"],
            {
                "ended_at": "2026-01-02T10:08:00",
                "summary": "状态不佳，先缓一缓",
                "next_step": "午休后做10分钟",
            },
        )["item"]
        self.assertEqual(abandoned["status"], "abandoned")

    def test_invalid_state_transition_rejected(self) -> None:
        app = self._make_app()
        item = self._start(app)
        app.complete_learning_session_payload(item["id"], {"ended_at": "2026-01-02T10:27:00"})
        with self.assertRaises(ValueError):
            app.abandon_learning_session_payload(item["id"], {})

    def test_actual_minutes_calculation(self) -> None:
        app = self._make_app()
        item = self._start(app, started_at="2026-01-02T09:00:00")
        completed = app.complete_learning_session_payload(
            item["id"], {"ended_at": "2026-01-02T09:42:00"}
        )["item"]
        self.assertEqual(completed["actual_minutes"], 42)

    def test_create_start_and_end_checkins(self) -> None:
        app = self._make_app()
        created = app.create_learning_session_payload(
            {
                "title": "英语复习",
                "goal": "复习20个单词",
                "mode": "recovery",
                "planned_minutes": 10,
                "start_checkin": {"energy_level": 2, "mood_level": 3, "note": "有点累"},
            }
        )["item"]
        app.complete_learning_session_payload(
            created["id"],
            {
                "ended_at": "2026-01-02T11:10:00",
                "end_checkin": {"focus_level": 3, "stress_level": 2, "note": "比预期好"},
            },
        )
        checkins = app.list_wellbeing_checkins_payload(created["id"])["items"]
        self.assertEqual(len(checkins), 2)
        stages = {item["stage"] for item in checkins}
        self.assertEqual(stages, {"start", "end"})

    def test_low_energy_start_generates_event(self) -> None:
        app = self._make_app()
        created = app.create_learning_session_payload(
            {
                "title": "英语复习",
                "goal": "复习20个单词",
                "mode": "recovery",
                "planned_minutes": 10,
                "start_checkin": {"energy_level": 1, "stress_level": 4, "note": "有点累，快撑不住"},
            }
        )["item"]
        event_types = [event["event_type"] for event in app.list_learning_session_events_payload(created["id"])["items"]]
        self.assertIn("low_energy_start", event_types)

    def test_style_config_affects_response_selection(self) -> None:
        app = self._make_app()
        item = self._start(app)
        app.update_learning_response_style_payload({"dominance_style": "high", "correction_style": "firm"}, session_id=item["id"])
        app.update_learning_session_runtime_payload(item["id"], {"action": "pause", "elapsed_minutes": 6, "remaining_minutes": 9})
        app.update_learning_session_runtime_payload(item["id"], {"action": "paused_too_long"})
        responses = app.list_learning_session_responses_payload(item["id"])["items"]
        paused_too_long = next(resp for resp in responses if resp["event_type"] == "session_paused_too_long")
        self.assertIn("不要继续往后拖", paused_too_long["message"])

    def test_firm_vs_caring_response_behavior(self) -> None:
        app = self._make_app()
        firm = self._start(app, title="高强度")
        app.update_learning_response_style_payload({"dominance_style": "high", "correction_style": "firm"}, session_id=firm["id"])
        app.update_learning_session_runtime_payload(firm["id"], {"action": "pause", "elapsed_minutes": 7, "remaining_minutes": 8})
        app.update_learning_session_runtime_payload(firm["id"], {"action": "paused_too_long"})
        firm_message = next(resp["message"] for resp in app.list_learning_session_responses_payload(firm["id"])["items"] if resp["event_type"] == "session_paused_too_long")

        app.complete_learning_session_payload(firm["id"], {"ended_at": "2026-01-02T10:15:00"})
        caring = self._start(app, title="低能量", start_checkin={"energy_level": 1, "stress_level": 5, "note": "好累"})
        app.update_learning_session_runtime_payload(caring["id"], {"action": "pause", "elapsed_minutes": 2, "remaining_minutes": 13})
        app.update_learning_session_runtime_payload(caring["id"], {"action": "paused_too_long"})
        caring_message = next(resp["message"] for resp in app.list_learning_session_responses_payload(caring["id"])["items"] if resp["event_type"] == "session_paused_too_long")
        self.assertNotEqual(firm_message, caring_message)
        self.assertIn("体面收尾", caring_message)

    def test_safety_constraint_no_degrading_output(self) -> None:
        app = self._make_app()
        item = self._start(app)
        app.update_learning_response_style_payload({"dominance_style": "high", "praise_style": "possessive_lite"}, session_id=item["id"])
        app.complete_learning_session_payload(item["id"], {"ended_at": "2026-01-02T10:20:00"})
        for response in app.list_learning_session_responses_payload(item["id"])["items"]:
            lowered = response["message"].lower()
            for banned in ["punish", "worthless", "idiot", "stupid", "humiliate"]:
                self.assertNotIn(banned, lowered)

    def test_list_current_active_session(self) -> None:
        app = self._make_app()
        created = self._start(app)
        active = app.get_active_learning_session_payload()["item"]
        self.assertEqual(active["id"], created["id"])

    def test_list_recent_sessions(self) -> None:
        app = self._make_app()
        first = self._start(app, title="会话A")
        app.complete_learning_session_payload(first["id"], {"ended_at": "2026-01-02T10:20:00"})
        second = self._start(app, title="会话B")
        app.abandon_learning_session_payload(second["id"], {"ended_at": "2026-01-02T11:15:00"})
        listed = app.list_learning_sessions_payload(limit=5)["items"]
        self.assertEqual(len(listed), 2)
        self.assertIn(listed[0]["status"], {"completed", "abandoned"})

    def test_retrieve_associated_checkins(self) -> None:
        app = self._make_app()
        created = self._start(app)
        app.add_wellbeing_checkin_payload(created["id"], {"stage": "start", "focus_level": 3})
        app.add_wellbeing_checkin_payload(created["id"], {"stage": "end", "note": "今天到这里"})
        payload = app.list_wellbeing_checkins_payload(created["id"])
        self.assertEqual(payload["session_id"], created["id"])
        self.assertEqual(len(payload["items"]), 2)

    def test_inspection_lists_events_responses_style_and_framework(self) -> None:
        app = self._make_app()
        created = self._start(app)
        app.update_learning_response_style_payload({"care_style": "soft"}, session_id=created["id"])
        app.update_learning_session_runtime_payload(created["id"], {"action": "focus_completed", "elapsed_minutes": 15, "remaining_minutes": 0})
        events = app.list_learning_session_events_payload(created["id"])["items"]
        responses = app.list_learning_session_responses_payload(created["id"])["items"]
        style = app.get_learning_response_style_payload(created["id"])["style"]
        framework = app.get_learning_response_framework_payload(created["id"])["framework"]
        self.assertGreaterEqual(len(events), 2)
        self.assertGreaterEqual(len(responses), 1)
        self.assertEqual(style["care_style"], "soft")
        self.assertIn("layered_persona", framework)
        self.assertEqual(responses[0]["response_context"]["safety"]["explicit_language_allowed"], False)

    def test_framework_is_persona_ready_without_custom_persona_content(self) -> None:
        app = self._make_app()
        created = self._start(app, mode="review")
        framework = app.get_learning_response_framework_payload(created["id"])["framework"]
        self.assertEqual(framework["layered_persona"]["base_persona_slot"], "neutral_companion")
        self.assertEqual(framework["mode_overlay"], "study_review")
        self.assertIn("Future persona injection", framework["todo"])


if __name__ == "__main__":
    unittest.main()
