from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


def utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


@dataclass
class SessionRecord:
    session_id: str
    profile_id: str
    channel: str
    channel_user_id: str
    chat_id: str
    thread_id: str
    status: str
    created_at: str
    updated_at: str
    last_activity_at: str


@dataclass
class ReminderRecord:
    reminder_id: str
    profile_id: str
    content: str
    trigger_at: str
    status: str
    channel: str
    created_at: str
    updated_at: str
    metadata: Dict[str, Any]
    delivered_at: str = ""




@dataclass
class LearningSessionRecord:
    session_id: str
    title: str
    goal: str
    subject: str
    mode: str
    status: str
    runtime_state: str
    planned_minutes: int
    pomodoro_count: int
    elapsed_minutes: int
    remaining_minutes: int
    break_count: int
    short_break_minutes: int
    long_break_minutes: int
    pause_started_at: str
    started_at: str
    ended_at: str
    actual_minutes: int
    summary: str
    blockers: str
    next_step: str
    created_at: str
    updated_at: str




@dataclass
class LearningSessionEventRecord:
    event_id: int
    session_id: str
    event_type: str
    runtime_state: str
    payload: Dict[str, Any]
    created_at: str


@dataclass
class LearningSessionResponseRecord:
    response_id: int
    session_id: str
    event_id: int
    event_type: str
    message: str
    style_config: Dict[str, Any]
    delivery_status: str
    created_at: str


@dataclass
class LearningResponseStyleRecord:
    style_id: int
    scope: str
    scope_id: str
    dominance_style: str
    care_style: str
    praise_style: str
    correction_style: str
    created_at: str
    updated_at: str

@dataclass
class WellbeingCheckinRecord:
    checkin_id: str
    session_id: str
    stage: str
    energy_level: Optional[int]
    focus_level: Optional[int]
    mood_level: Optional[int]
    body_state_level: Optional[int]
    stress_level: Optional[int]
    note: str
    created_at: str

class RuntimeStore:
    def __init__(self, db_path: Path, event_log_path: Path):
        self.db_path = db_path
        self.event_log_path = event_log_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA busy_timeout=5000")
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self.conn.executescript(
                """
            CREATE TABLE IF NOT EXISTS profiles (
              profile_id TEXT PRIMARY KEY,
              last_channel TEXT DEFAULT '',
              channel_user_id TEXT DEFAULT '',
              chat_id TEXT DEFAULT '',
              thread_id TEXT DEFAULT '',
              last_session_id TEXT DEFAULT '',
              last_interaction_at TEXT NOT NULL,
              last_proactive_at TEXT DEFAULT '',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
              session_id TEXT PRIMARY KEY,
              profile_id TEXT NOT NULL,
              channel TEXT DEFAULT '',
              channel_user_id TEXT DEFAULT '',
              chat_id TEXT DEFAULT '',
              thread_id TEXT DEFAULT '',
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              last_activity_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_profile_activity
            ON sessions(profile_id, last_activity_at DESC);

            CREATE TABLE IF NOT EXISTS session_messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL,
              profile_id TEXT NOT NULL,
              role TEXT NOT NULL,
              content TEXT NOT NULL,
              channel TEXT DEFAULT '',
              metadata TEXT DEFAULT '{}',
              created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_session_messages_session_id
            ON session_messages(session_id, id DESC);

            CREATE TABLE IF NOT EXISTS reminders (
              reminder_id TEXT PRIMARY KEY,
              profile_id TEXT NOT NULL,
              content TEXT NOT NULL,
              trigger_at TEXT NOT NULL,
              status TEXT NOT NULL,
              channel TEXT DEFAULT '',
              metadata TEXT DEFAULT '{}',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              delivered_at TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_reminders_trigger
            ON reminders(status, trigger_at);

            CREATE TABLE IF NOT EXISTS learning_sessions (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL DEFAULT '',
              goal TEXT NOT NULL DEFAULT '',
              subject TEXT NOT NULL DEFAULT '',
              mode TEXT NOT NULL DEFAULT 'focus',
              status TEXT NOT NULL DEFAULT 'active',
              runtime_state TEXT NOT NULL DEFAULT 'focus',
              planned_minutes INTEGER NOT NULL DEFAULT 25,
              pomodoro_count INTEGER NOT NULL DEFAULT 0,
              elapsed_minutes INTEGER NOT NULL DEFAULT 0,
              remaining_minutes INTEGER NOT NULL DEFAULT 0,
              break_count INTEGER NOT NULL DEFAULT 0,
              short_break_minutes INTEGER NOT NULL DEFAULT 5,
              long_break_minutes INTEGER NOT NULL DEFAULT 15,
              pause_started_at TEXT NOT NULL DEFAULT '',
              started_at TEXT NOT NULL DEFAULT '',
              ended_at TEXT NOT NULL DEFAULT '',
              actual_minutes INTEGER NOT NULL DEFAULT 0,
              summary TEXT NOT NULL DEFAULT '',
              blockers TEXT NOT NULL DEFAULT '',
              next_step TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_learning_sessions_status_updated
            ON learning_sessions(status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS wellbeing_checkins (
              id TEXT PRIMARY KEY,
              session_id TEXT NOT NULL,
              stage TEXT NOT NULL,
              energy_level INTEGER,
              focus_level INTEGER,
              mood_level INTEGER,
              body_state_level INTEGER,
              stress_level INTEGER,
              note TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_wellbeing_checkins_session_created
            ON wellbeing_checkins(session_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS learning_session_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              runtime_state TEXT NOT NULL DEFAULT '',
              payload TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_learning_session_events_session_created
            ON learning_session_events(session_id, id DESC);

            CREATE TABLE IF NOT EXISTS learning_session_responses (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL,
              event_id INTEGER NOT NULL DEFAULT 0,
              event_type TEXT NOT NULL,
              message TEXT NOT NULL,
              style_config TEXT NOT NULL DEFAULT '{}',
              delivery_status TEXT NOT NULL DEFAULT 'queued',
              created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_learning_session_responses_session_created
            ON learning_session_responses(session_id, id DESC);

            CREATE TABLE IF NOT EXISTS learning_response_styles (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              scope TEXT NOT NULL DEFAULT 'default',
              scope_id TEXT NOT NULL DEFAULT '',
              dominance_style TEXT NOT NULL DEFAULT 'medium',
              care_style TEXT NOT NULL DEFAULT 'steady',
              praise_style TEXT NOT NULL DEFAULT 'warm',
              correction_style TEXT NOT NULL DEFAULT 'gentle',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_learning_response_styles_scope
            ON learning_response_styles(scope, scope_id);

            CREATE TABLE IF NOT EXISTS gateway_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_type TEXT NOT NULL,
              profile_id TEXT DEFAULT '',
              session_id TEXT DEFAULT '',
              channel TEXT DEFAULT '',
              payload TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
                """
            )
            self._ensure_column("learning_sessions", "runtime_state", "TEXT NOT NULL DEFAULT 'focus'")
            self._ensure_column("learning_sessions", "elapsed_minutes", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("learning_sessions", "remaining_minutes", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("learning_sessions", "break_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("learning_sessions", "short_break_minutes", "INTEGER NOT NULL DEFAULT 5")
            self._ensure_column("learning_sessions", "long_break_minutes", "INTEGER NOT NULL DEFAULT 15")
            self._ensure_column("learning_sessions", "pause_started_at", "TEXT NOT NULL DEFAULT ''")
            self.conn.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {
            str(row["name"])
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def resolve_session(
        self,
        *,
        profile_id: str,
        channel: str = "",
        channel_user_id: str = "",
        chat_id: str = "",
        thread_id: str = "",
        idle_rotation_minutes: int = 360,
    ) -> SessionRecord:
        now = utcnow_iso()
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM sessions WHERE profile_id = ? ORDER BY last_activity_at DESC LIMIT 1",
                (profile_id,),
            ).fetchone()
            session_id = ""
            if row is not None:
                last_activity = self._parse_time(str(row["last_activity_at"]))
                if datetime.utcnow() - last_activity <= timedelta(
                    minutes=max(idle_rotation_minutes, 1)
                ):
                    session_id = str(row["session_id"])
                    self.conn.execute(
                        """
                        UPDATE sessions
                        SET channel = ?, channel_user_id = ?, chat_id = ?, thread_id = ?, updated_at = ?, last_activity_at = ?
                        WHERE session_id = ?
                        """,
                        (
                            channel,
                            channel_user_id,
                            chat_id,
                            thread_id,
                            now,
                            now,
                            session_id,
                        ),
                    )
            if not session_id:
                session_id = f"sess_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
                self.conn.execute(
                    """
                    INSERT INTO sessions(session_id, profile_id, channel, channel_user_id, chat_id, thread_id, status, created_at, updated_at, last_activity_at)
                    VALUES(?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                    """,
                    (
                        session_id,
                        profile_id,
                        channel,
                        channel_user_id,
                        chat_id,
                        thread_id,
                        now,
                        now,
                        now,
                    ),
                )
            self._touch_profile(
                profile_id=profile_id,
                channel=channel,
                channel_user_id=channel_user_id,
                chat_id=chat_id,
                thread_id=thread_id,
                session_id=session_id,
                interaction_at=now,
            )
            self.conn.commit()
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> SessionRecord:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise KeyError("session not found")
        return self._row_to_session(row)

    def list_sessions(
        self, profile_id: str = "", limit: int = 20
    ) -> List[SessionRecord]:
        with self._lock:
            if profile_id:
                rows = self.conn.execute(
                    "SELECT * FROM sessions WHERE profile_id = ? ORDER BY last_activity_at DESC LIMIT ?",
                    (profile_id, limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM sessions ORDER BY last_activity_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def append_message(
        self,
        *,
        session_id: str,
        profile_id: str,
        role: str,
        content: str,
        channel: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = utcnow_iso()
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO session_messages(session_id, profile_id, role, content, channel, metadata, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    profile_id,
                    role,
                    content,
                    channel,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                ),
            )
            self.conn.execute(
                "UPDATE sessions SET updated_at = ?, last_activity_at = ? WHERE session_id = ?",
                (now, now, session_id),
            )
            self._touch_profile(
                profile_id=profile_id,
                channel=channel,
                session_id=session_id,
                interaction_at=now,
            )
            self.conn.commit()

    def list_recent_messages(
        self, session_id: str, limit: int = 30
    ) -> List[Dict[str, str]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT role, content FROM session_messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        items = [
            {"role": str(row["role"]), "content": str(row["content"])}
            for row in reversed(rows)
        ]
        return items

    def list_messages_between(
        self,
        *,
        profile_id: str = "",
        session_id: str = "",
        start_at: str = "",
        end_at: str = "",
        limit: int = 2000,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        values: List[Any] = []
        if profile_id:
            clauses.append("profile_id = ?")
            values.append(profile_id)
        if session_id:
            clauses.append("session_id = ?")
            values.append(session_id)
        if start_at:
            clauses.append("created_at >= ?")
            values.append(start_at)
        if end_at:
            clauses.append("created_at < ?")
            values.append(end_at)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT id, session_id, profile_id, role, content, channel, metadata, created_at
                FROM session_messages
                {where}
                ORDER BY id ASC
                LIMIT ?
                """,
                (*values, limit),
            ).fetchall()
        items: List[Dict[str, Any]] = []
        for row in rows:
            try:
                metadata = json.loads(str(row["metadata"] or "{}"))
            except json.JSONDecodeError:
                metadata = {"raw": row["metadata"]}
            items.append(
                {
                    "id": int(row["id"]),
                    "session_id": str(row["session_id"]),
                    "profile_id": str(row["profile_id"]),
                    "role": str(row["role"]),
                    "content": str(row["content"]),
                    "channel": str(row["channel"] or ""),
                    "metadata": metadata,
                    "created_at": str(row["created_at"]),
                }
            )
        return items

    def count_messages_between(
        self,
        *,
        profile_id: str = "",
        session_id: str = "",
        start_at: str = "",
        end_at: str = "",
    ) -> int:
        clauses: List[str] = []
        values: List[Any] = []
        if profile_id:
            clauses.append("profile_id = ?")
            values.append(profile_id)
        if session_id:
            clauses.append("session_id = ?")
            values.append(session_id)
        if start_at:
            clauses.append("created_at >= ?")
            values.append(start_at)
        if end_at:
            clauses.append("created_at < ?")
            values.append(end_at)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            row = self.conn.execute(
                f"SELECT COUNT(*) AS count FROM session_messages {where}",
                tuple(values),
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def add_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        profile_id: str = "",
        session_id: str = "",
        channel: str = "",
    ) -> None:
        now = utcnow_iso()
        payload_text = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO gateway_events(event_type, profile_id, session_id, channel, payload, created_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (event_type, profile_id, session_id, channel, payload_text, now),
            )
            self.conn.commit()
            log_entry = {
                "event_type": event_type,
                "profile_id": profile_id,
                "session_id": session_id,
                "channel": channel,
                "payload": payload,
                "created_at": now,
            }
            with self.event_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def list_events(
        self, profile_id: str = "", session_id: str = "", limit: int = 50
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        values: List[Any] = []
        if profile_id:
            clauses.append("profile_id = ?")
            values.append(profile_id)
        if session_id:
            clauses.append("session_id = ?")
            values.append(session_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self.conn.execute(
                f"SELECT * FROM gateway_events {where} ORDER BY id DESC LIMIT ?",
                (*values, limit),
            ).fetchall()
        items: List[Dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload"] or "{}"))
            except json.JSONDecodeError:
                payload = {"raw": row["payload"]}
            items.append(
                {
                    "id": int(row["id"]),
                    "event_type": str(row["event_type"]),
                    "profile_id": str(row["profile_id"] or ""),
                    "session_id": str(row["session_id"] or ""),
                    "channel": str(row["channel"] or ""),
                    "payload": payload,
                    "created_at": str(row["created_at"]),
                }
            )
        return items

    def create_reminder(
        self,
        *,
        reminder_id: str,
        profile_id: str,
        content: str,
        trigger_at: str,
        channel: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReminderRecord:
        now = utcnow_iso()
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO reminders(reminder_id, profile_id, content, trigger_at, status, channel, metadata, created_at, updated_at, delivered_at)
                VALUES(?, ?, ?, ?, 'pending', ?, ?, ?, ?, '')
                """,
                (
                    reminder_id,
                    profile_id,
                    content,
                    trigger_at,
                    channel,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            self.conn.commit()
        return self.get_reminder(reminder_id)

    def get_reminder(self, reminder_id: str) -> ReminderRecord:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM reminders WHERE reminder_id = ?", (reminder_id,)
            ).fetchone()
        if row is None:
            raise KeyError("reminder not found")
        return self._row_to_reminder(row)

    def list_reminders(
        self, profile_id: str = "", status: str = "", limit: int = 100
    ) -> List[ReminderRecord]:
        clauses: List[str] = []
        values: List[Any] = []
        if profile_id:
            clauses.append("profile_id = ?")
            values.append(profile_id)
        if status:
            clauses.append("status = ?")
            values.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self.conn.execute(
                f"SELECT * FROM reminders {where} ORDER BY trigger_at ASC LIMIT ?",
                (*values, limit),
            ).fetchall()
        return [self._row_to_reminder(row) for row in rows]

    def list_due_reminders(
        self, now_iso: Optional[str] = None, limit: int = 20
    ) -> List[ReminderRecord]:
        moment = now_iso or utcnow_iso()
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM reminders
                WHERE status = 'pending' AND trigger_at <= ?
                ORDER BY trigger_at ASC
                LIMIT ?
                """,
                (moment, limit),
            ).fetchall()
        return [self._row_to_reminder(row) for row in rows]

    def mark_reminder_delivered(self, reminder_id: str) -> None:
        now = utcnow_iso()
        with self._lock:
            self.conn.execute(
                "UPDATE reminders SET status = 'delivered', updated_at = ?, delivered_at = ? WHERE reminder_id = ?",
                (now, now, reminder_id),
            )
            self.conn.commit()

    def delete_reminder(self, reminder_id: str) -> bool:
        with self._lock:
            cursor = self.conn.execute(
                "DELETE FROM reminders WHERE reminder_id = ?", (reminder_id,)
            )
            self.conn.commit()
        return cursor.rowcount > 0

    def get_active_learning_session(self) -> Optional[LearningSessionRecord]:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM learning_sessions WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return self._row_to_learning_session(row) if row is not None else None

    def create_learning_session(
        self,
        *,
        session_id: str,
        title: str,
        goal: str,
        subject: str,
        mode: str,
        planned_minutes: int,
        pomodoro_count: int,
        short_break_minutes: int,
        long_break_minutes: int,
        started_at: str,
    ) -> LearningSessionRecord:
        now = utcnow_iso()
        with self._lock:
            active = self.conn.execute(
                "SELECT id FROM learning_sessions WHERE status = 'active' LIMIT 1"
            ).fetchone()
            if active is not None:
                raise ValueError("active_learning_session_exists")
            self.conn.execute(
                """
                INSERT INTO learning_sessions(
                  id, title, goal, subject, mode, status, runtime_state, planned_minutes, pomodoro_count,
                  elapsed_minutes, remaining_minutes, break_count, short_break_minutes, long_break_minutes, pause_started_at,
                  started_at, ended_at, actual_minutes, summary, blockers, next_step, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, 'active', 'focus', ?, ?, 0, ?, 0, ?, ?, '', ?, '', 0, '', '', '', ?, ?)
                """,
                (
                    session_id,
                    title,
                    goal,
                    subject,
                    mode,
                    planned_minutes,
                    pomodoro_count,
                    planned_minutes,
                    short_break_minutes,
                    long_break_minutes,
                    started_at,
                    now,
                    now,
                ),
            )
            self.conn.commit()
        return self.get_learning_session(session_id)

    def get_learning_session(self, session_id: str) -> LearningSessionRecord:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM learning_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise KeyError("learning session not found")
        return self._row_to_learning_session(row)

    def list_learning_sessions(self, *, status: str = "", limit: int = 20) -> List[LearningSessionRecord]:
        with self._lock:
            if status:
                rows = self.conn.execute(
                    "SELECT * FROM learning_sessions WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM learning_sessions ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_learning_session(row) for row in rows]

    def update_learning_session(self, session_id: str, fields: Dict[str, Any]) -> LearningSessionRecord:
        allowed_fields = {
            "title",
            "goal",
            "subject",
            "mode",
            "planned_minutes",
            "pomodoro_count",
            "summary",
            "blockers",
            "next_step",
            "runtime_state",
            "elapsed_minutes",
            "remaining_minutes",
            "break_count",
            "short_break_minutes",
            "long_break_minutes",
            "pause_started_at",
        }
        assignments = []
        values: List[Any] = []
        for key, value in fields.items():
            if key not in allowed_fields:
                continue
            assignments.append(f"{key} = ?")
            values.append(value)
        if not assignments:
            return self.get_learning_session(session_id)
        now = utcnow_iso()
        with self._lock:
            values.extend([now, session_id])
            self.conn.execute(
                f"UPDATE learning_sessions SET {', '.join(assignments)}, updated_at = ? WHERE id = ?",
                tuple(values),
            )
            self.conn.commit()
        return self.get_learning_session(session_id)

    def set_learning_session_runtime_state(
        self,
        session_id: str,
        *,
        runtime_state: str,
        pause_started_at: Optional[str] = None,
        elapsed_minutes: Optional[int] = None,
        remaining_minutes: Optional[int] = None,
        break_count: Optional[int] = None,
        pomodoro_count: Optional[int] = None,
    ) -> LearningSessionRecord:
        assignments = ["runtime_state = ?"]
        values: List[Any] = [runtime_state]
        if pause_started_at is not None:
            assignments.append("pause_started_at = ?")
            values.append(pause_started_at)
        if elapsed_minutes is not None:
            assignments.append("elapsed_minutes = ?")
            values.append(max(0, elapsed_minutes))
        if remaining_minutes is not None:
            assignments.append("remaining_minutes = ?")
            values.append(max(0, remaining_minutes))
        if break_count is not None:
            assignments.append("break_count = ?")
            values.append(max(0, break_count))
        if pomodoro_count is not None:
            assignments.append("pomodoro_count = ?")
            values.append(max(0, pomodoro_count))
        now = utcnow_iso()
        with self._lock:
            values.extend([now, session_id])
            self.conn.execute(
                f"UPDATE learning_sessions SET {', '.join(assignments)}, updated_at = ? WHERE id = ?",
                tuple(values),
            )
            self.conn.commit()
        return self.get_learning_session(session_id)

    def transition_learning_session(
        self,
        *,
        session_id: str,
        target_status: str,
        ended_at: str = "",
        summary: str = "",
        blockers: str = "",
        next_step: str = "",
        actual_minutes: Optional[int] = None,
    ) -> LearningSessionRecord:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM learning_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise KeyError("learning session not found")
            current_status = str(row["status"] or "")
            if current_status != "active":
                raise ValueError("learning_session_not_active")
            now = utcnow_iso()
            final_ended_at = ended_at or now
            final_actual_minutes = int(actual_minutes if actual_minutes is not None else row["actual_minutes"] or 0)
            self.conn.execute(
                """
                UPDATE learning_sessions
                SET status = ?, runtime_state = CASE WHEN ? = 'completed' THEN 'completed' ELSE 'abandoned' END,
                    ended_at = ?, actual_minutes = ?, remaining_minutes = 0, pause_started_at = '',
                    summary = CASE WHEN ? != '' THEN ? ELSE summary END,
                    blockers = CASE WHEN ? != '' THEN ? ELSE blockers END,
                    next_step = CASE WHEN ? != '' THEN ? ELSE next_step END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    target_status,
                    target_status,
                    final_ended_at,
                    final_actual_minutes,
                    summary,
                    summary,
                    blockers,
                    blockers,
                    next_step,
                    next_step,
                    now,
                    session_id,
                ),
            )
            self.conn.commit()
        return self.get_learning_session(session_id)

    def add_learning_session_event(
        self,
        *,
        session_id: str,
        event_type: str,
        runtime_state: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> LearningSessionEventRecord:
        now = utcnow_iso()
        payload_text = json.dumps(payload or {}, ensure_ascii=False)
        with self._lock:
            cursor = self.conn.execute(
                """
                INSERT INTO learning_session_events(session_id, event_type, runtime_state, payload, created_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (session_id, event_type, runtime_state, payload_text, now),
            )
            self.conn.commit()
            event_id = int(cursor.lastrowid)
        return self.get_learning_session_event(event_id)

    def get_learning_session_event(self, event_id: int) -> LearningSessionEventRecord:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM learning_session_events WHERE id = ?",
                (event_id,),
            ).fetchone()
        if row is None:
            raise KeyError("learning session event not found")
        return self._row_to_learning_session_event(row)

    def list_learning_session_events(self, *, session_id: str, limit: int = 20) -> List[LearningSessionEventRecord]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM learning_session_events WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [self._row_to_learning_session_event(row) for row in rows]

    def add_learning_session_response(
        self,
        *,
        session_id: str,
        event_id: int,
        event_type: str,
        message: str,
        style_config: Optional[Dict[str, Any]] = None,
        delivery_status: str = "queued",
    ) -> LearningSessionResponseRecord:
        now = utcnow_iso()
        with self._lock:
            cursor = self.conn.execute(
                """
                INSERT INTO learning_session_responses(session_id, event_id, event_type, message, style_config, delivery_status, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    event_id,
                    event_type,
                    message,
                    json.dumps(style_config or {}, ensure_ascii=False),
                    delivery_status,
                    now,
                ),
            )
            self.conn.commit()
            response_id = int(cursor.lastrowid)
        return self.get_learning_session_response(response_id)

    def get_learning_session_response(self, response_id: int) -> LearningSessionResponseRecord:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM learning_session_responses WHERE id = ?",
                (response_id,),
            ).fetchone()
        if row is None:
            raise KeyError("learning session response not found")
        return self._row_to_learning_session_response(row)

    def list_learning_session_responses(self, *, session_id: str, limit: int = 20) -> List[LearningSessionResponseRecord]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM learning_session_responses WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [self._row_to_learning_session_response(row) for row in rows]

    def upsert_learning_response_style(
        self,
        *,
        scope: str,
        scope_id: str,
        dominance_style: str,
        care_style: str,
        praise_style: str,
        correction_style: str,
    ) -> LearningResponseStyleRecord:
        now = utcnow_iso()
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO learning_response_styles(
                  scope, scope_id, dominance_style, care_style, praise_style, correction_style, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope, scope_id) DO UPDATE SET
                  dominance_style=excluded.dominance_style,
                  care_style=excluded.care_style,
                  praise_style=excluded.praise_style,
                  correction_style=excluded.correction_style,
                  updated_at=excluded.updated_at
                """,
                (scope, scope_id, dominance_style, care_style, praise_style, correction_style, now, now),
            )
            self.conn.commit()
        return self.get_learning_response_style(scope=scope, scope_id=scope_id)

    def get_learning_response_style(self, *, scope: str = "default", scope_id: str = "") -> Optional[LearningResponseStyleRecord]:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM learning_response_styles WHERE scope = ? AND scope_id = ?",
                (scope, scope_id),
            ).fetchone()
        return self._row_to_learning_response_style(row) if row is not None else None

    def add_wellbeing_checkin(
        self,
        *,
        checkin_id: str,
        session_id: str,
        stage: str,
        energy_level: Optional[int] = None,
        focus_level: Optional[int] = None,
        mood_level: Optional[int] = None,
        body_state_level: Optional[int] = None,
        stress_level: Optional[int] = None,
        note: str = "",
    ) -> WellbeingCheckinRecord:
        now = utcnow_iso()
        with self._lock:
            exists = self.conn.execute(
                "SELECT id FROM learning_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if exists is None:
                raise KeyError("learning session not found")
            self.conn.execute(
                """
                INSERT INTO wellbeing_checkins(
                  id, session_id, stage, energy_level, focus_level, mood_level, body_state_level, stress_level, note, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkin_id,
                    session_id,
                    stage,
                    energy_level,
                    focus_level,
                    mood_level,
                    body_state_level,
                    stress_level,
                    note,
                    now,
                ),
            )
            self.conn.commit()
        return self.get_wellbeing_checkin(checkin_id)

    def get_wellbeing_checkin(self, checkin_id: str) -> WellbeingCheckinRecord:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM wellbeing_checkins WHERE id = ?", (checkin_id,)
            ).fetchone()
        if row is None:
            raise KeyError("wellbeing checkin not found")
        return self._row_to_wellbeing_checkin(row)

    def list_wellbeing_checkins(self, *, session_id: str, limit: int = 20) -> List[WellbeingCheckinRecord]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM wellbeing_checkins WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [self._row_to_wellbeing_checkin(row) for row in rows]

    def list_inactive_profiles(
        self,
        *,
        idle_hours: int,
        proactive_cooldown_hours: int,
        limit: int = 10,
        idle_minutes: int = 0,
    ) -> List[Dict[str, str]]:
        idle_delta = timedelta(
            minutes=max(idle_minutes, 0),
            hours=max(idle_hours, 0),
        )
        if idle_delta.total_seconds() <= 0:
            idle_delta = timedelta(hours=1)
        cutoff = (datetime.utcnow() - idle_delta).isoformat()
        cooldown_cutoff = (
            datetime.utcnow() - timedelta(hours=max(proactive_cooldown_hours, 1))
        ).isoformat()
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM profiles
                WHERE last_interaction_at <= ?
                  AND (last_proactive_at = '' OR last_proactive_at <= ?)
                  AND channel_user_id != ''
                ORDER BY last_interaction_at ASC
                LIMIT ?
                """,
                (cutoff, cooldown_cutoff, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_proactive_sent(self, profile_id: str) -> None:
        now = utcnow_iso()
        with self._lock:
            self.conn.execute(
                "UPDATE profiles SET last_proactive_at = ?, updated_at = ? WHERE profile_id = ?",
                (now, now, profile_id),
            )
            self.conn.commit()

    def profile_state(self, profile_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM profiles WHERE profile_id = ?", (profile_id,)
            ).fetchone()
        if row is None:
            return {}
        return dict(row)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "profiles": self._count("profiles"),
                "sessions": self._count("sessions"),
                "reminders": self._count("reminders"),
                "events": self._count("gateway_events"),
                "learning_sessions": self._count("learning_sessions"),
                "wellbeing_checkins": self._count("wellbeing_checkins"),
            }

    def _count(self, table: str) -> int:
        with self._lock:
            row = self.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"]) if row is not None else 0

    def _touch_profile(
        self,
        *,
        profile_id: str,
        channel: str = "",
        channel_user_id: str = "",
        chat_id: str = "",
        thread_id: str = "",
        session_id: str = "",
        interaction_at: Optional[str] = None,
    ) -> None:
        now = interaction_at or utcnow_iso()
        existing = self.conn.execute(
            "SELECT * FROM profiles WHERE profile_id = ?", (profile_id,)
        ).fetchone()
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO profiles(profile_id, last_channel, channel_user_id, chat_id, thread_id, last_session_id, last_interaction_at, last_proactive_at, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, '', ?, ?)
                """,
                (
                    profile_id,
                    channel,
                    channel_user_id,
                    chat_id,
                    thread_id,
                    session_id,
                    now,
                    now,
                    now,
                ),
            )
            return
        self.conn.execute(
            """
            UPDATE profiles
            SET last_channel = ?,
                channel_user_id = CASE WHEN ? != '' THEN ? ELSE channel_user_id END,
                chat_id = CASE WHEN ? != '' THEN ? ELSE chat_id END,
                thread_id = CASE WHEN ? != '' THEN ? ELSE thread_id END,
                last_session_id = CASE WHEN ? != '' THEN ? ELSE last_session_id END,
                last_interaction_at = ?,
                updated_at = ?
            WHERE profile_id = ?
            """,
            (
                channel or str(existing["last_channel"]),
                channel_user_id,
                channel_user_id,
                chat_id,
                chat_id,
                thread_id,
                thread_id,
                session_id,
                session_id,
                now,
                now,
                profile_id,
            ),
        )

    def _row_to_session(self, row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            session_id=str(row["session_id"]),
            profile_id=str(row["profile_id"]),
            channel=str(row["channel"] or ""),
            channel_user_id=str(row["channel_user_id"] or ""),
            chat_id=str(row["chat_id"] or ""),
            thread_id=str(row["thread_id"] or ""),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            last_activity_at=str(row["last_activity_at"]),
        )

    def _row_to_reminder(self, row: sqlite3.Row) -> ReminderRecord:
        try:
            metadata = json.loads(str(row["metadata"] or "{}"))
        except json.JSONDecodeError:
            metadata = {"raw": row["metadata"]}
        return ReminderRecord(
            reminder_id=str(row["reminder_id"]),
            profile_id=str(row["profile_id"]),
            content=str(row["content"]),
            trigger_at=str(row["trigger_at"]),
            status=str(row["status"]),
            channel=str(row["channel"] or ""),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            metadata=metadata,
            delivered_at=str(row["delivered_at"] or ""),
        )

    def _row_to_learning_session(self, row: sqlite3.Row) -> LearningSessionRecord:
        return LearningSessionRecord(
            session_id=str(row["id"]),
            title=str(row["title"] or ""),
            goal=str(row["goal"] or ""),
            subject=str(row["subject"] or ""),
            mode=str(row["mode"] or "focus"),
            status=str(row["status"] or "active"),
            runtime_state=str(row["runtime_state"] or "focus"),
            planned_minutes=int(row["planned_minutes"] or 0),
            pomodoro_count=int(row["pomodoro_count"] or 0),
            elapsed_minutes=int(row["elapsed_minutes"] or 0),
            remaining_minutes=int(row["remaining_minutes"] or 0),
            break_count=int(row["break_count"] or 0),
            short_break_minutes=int(row["short_break_minutes"] or 5),
            long_break_minutes=int(row["long_break_minutes"] or 15),
            pause_started_at=str(row["pause_started_at"] or ""),
            started_at=str(row["started_at"] or ""),
            ended_at=str(row["ended_at"] or ""),
            actual_minutes=int(row["actual_minutes"] or 0),
            summary=str(row["summary"] or ""),
            blockers=str(row["blockers"] or ""),
            next_step=str(row["next_step"] or ""),
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )

    def _row_to_learning_session_event(self, row: sqlite3.Row) -> LearningSessionEventRecord:
        try:
            payload = json.loads(str(row["payload"] or "{}"))
        except json.JSONDecodeError:
            payload = {"raw": str(row["payload"] or "")}
        return LearningSessionEventRecord(
            event_id=int(row["id"]),
            session_id=str(row["session_id"] or ""),
            event_type=str(row["event_type"] or ""),
            runtime_state=str(row["runtime_state"] or ""),
            payload=payload,
            created_at=str(row["created_at"] or ""),
        )

    def _row_to_learning_session_response(self, row: sqlite3.Row) -> LearningSessionResponseRecord:
        try:
            style_config = json.loads(str(row["style_config"] or "{}"))
        except json.JSONDecodeError:
            style_config = {}
        return LearningSessionResponseRecord(
            response_id=int(row["id"]),
            session_id=str(row["session_id"] or ""),
            event_id=int(row["event_id"] or 0),
            event_type=str(row["event_type"] or ""),
            message=str(row["message"] or ""),
            style_config=style_config,
            delivery_status=str(row["delivery_status"] or ""),
            created_at=str(row["created_at"] or ""),
        )

    def _row_to_learning_response_style(self, row: sqlite3.Row) -> LearningResponseStyleRecord:
        return LearningResponseStyleRecord(
            style_id=int(row["id"]),
            scope=str(row["scope"] or ""),
            scope_id=str(row["scope_id"] or ""),
            dominance_style=str(row["dominance_style"] or "medium"),
            care_style=str(row["care_style"] or "steady"),
            praise_style=str(row["praise_style"] or "warm"),
            correction_style=str(row["correction_style"] or "gentle"),
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )

    def _row_to_wellbeing_checkin(self, row: sqlite3.Row) -> WellbeingCheckinRecord:
        return WellbeingCheckinRecord(
            checkin_id=str(row["id"]),
            session_id=str(row["session_id"]),
            stage=str(row["stage"] or ""),
            energy_level=int(row["energy_level"]) if row["energy_level"] is not None else None,
            focus_level=int(row["focus_level"]) if row["focus_level"] is not None else None,
            mood_level=int(row["mood_level"]) if row["mood_level"] is not None else None,
            body_state_level=int(row["body_state_level"]) if row["body_state_level"] is not None else None,
            stress_level=int(row["stress_level"]) if row["stress_level"] is not None else None,
            note=str(row["note"] or ""),
            created_at=str(row["created_at"] or ""),
        )

    def _parse_time(self, value: str) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.utcnow()
