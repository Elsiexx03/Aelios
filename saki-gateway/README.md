# Aelios Saki Gateway (Sanitized OSS Build)

This is a sanitized open-source version of the Python gateway used to power multi-channel chat, memory, reminders, web/image tools, and channel integrations.

## Included
- Python gateway runtime
- Feishu / QQBot channel integrations
- Memory store, runtime store, reminder scheduler
- Search / fetch / image-analysis tool plumbing

## Excluded from this OSS build
- Personal memories, conversation logs, profiles
- API keys, app tokens, webhook secrets
- Private PM2 / deployment specifics

## Quick start
1. Create a virtualenv
2. Install from `pyproject.toml`
3. Copy `data/config.example.json` to `data/config.json`
4. Fill your own provider and channel credentials
5. Run `python -m saki_gateway`

## Notes
This repository is intentionally sanitized for open-source release.

## Memory prompt flow
The runtime reply path now uses a cache-stable prompt order:
1. base persona/system prompt
2. fixed important memories (`importance = 1`)
3. today log
4. recent session context
5. latest user message
6. late-bound supplemental memory from the action runtime

The action runtime no longer relies on `search_memory` during normal replies. Instead, the gateway precomputes a candidate pool from non-fixed long-term memories plus today/yesterday logs, and the action runtime selects only concise missing details worth appending at the end.


## Short-term memory files (Phase 4 slice 1)
`data/core_profile.md` now renders in structured sections:
- `About Her`
- `Relationship Core`
- `My Profile`

`data/active_memory.md` now renders in structured sections:
- `Current Status`
- `Purpose Context`
- `On the Horizon`
- `Others`

Both files keep a backward-compatible timestamp header and add a format marker (`core_profile.v2` / `active_memory.v2`). Rendering is bounded by per-section item limits and per-item character limits to keep prompt token usage stable.


## Nightly digest scheduler (Phase 4 slice 2)
- Scheduler now uses local timezone-aware evaluation and triggers nightly digest once per local date at **04:05**.
- Timezone is configurable via `scheduler.local_timezone` (or env `SAKI_LOCAL_TIMEZONE`). If invalid/missing, gateway falls back to server local timezone.
- Digest run state is persisted to `memory.digest_run_state_path` (default `./data/digest_run_state.json`) with fields:
  - `id`, `run_state`, `status`, `started_at`, `completed_at`, `error_message`
- Idempotency behavior:
  - If a date already completed with `success`, scheduler records skip and does not rerun that date.
  - If a run fails (for example Trilium unavailable), status becomes `failed` and a later tick can retry safely.
- Digest inputs include recent 24h messages, tool execution events, active memory snapshot, and optional recent durable memories.
- Digest output refreshes `active_memory.md` and upserts one Trilium note under `AI Companion Workspace / Daily Digest / YYYY-MM-DD daily digest` (best-effort, graceful failure).

TODOs:
- core profile proposal queue (`pending_core_updates`) is intentionally out-of-scope for slice 2.
- durable-memory archival strategy remains intentionally minimal in this slice.


## Core profile protection + proposal workflow (Phase 4 slice 3)
- `core_profile.md` is protected: automatic jobs must not silently overwrite core sections.
- `active_memory.md` may still refresh automatically.
- Candidate core changes are stored in SQLite table `pending_core_updates` with fields:
  - `id`, `target_section`, `proposed_content`, `reason`, `source_context`, `fingerprint`, `proposal_type`, `confidence`, `status`, `created_at`, `updated_at`, `reviewed_at`
- `proposal_type` is constrained in practice to: `identity | preference | goal | relationship | routine | other`
- `confidence` is constrained in practice to: `low | medium | high`
- `target_section` is validated to the real core sections only:
  - `About Her`, `Relationship Core`, `My Profile`
- Fingerprint purpose:
  - deduplicate semantically same open proposals based on normalized section + normalized content
  - normalization collapses whitespace and strips trivial markdown-only prefixes
- Dedup behavior:
  - if same fingerprint already exists in `open` status, no new row is inserted; existing row `updated_at` is touched and context can be merged
  - approved/rejected history is preserved
- Review lifecycle (backend):
  - `open` -> `approved` performs section-aware semantic merge (dedupe + conservative conflict handling) and sets `reviewed_at`
  - `open` -> `rejected` keeps `core_profile` unchanged and sets `reviewed_at`
- Merge behavior for approval:
  - integrates meaningfully new entries once into the target section
  - suppresses strongly overlapping duplicates
  - handles likely conflicts conservatively (logs conflict, does not overwrite existing safer fact)

Known limitations:
- UI review panel is not included in this slice (backend operations only).
- Semantic merge is intentionally conservative; richer contradiction resolution and ontology-aware merging remain TODO.


## Review/admin visibility surface (Phase 4 slice 5)
A minimal backend review surface is available via authenticated dashboard API routes (no chat UI changes):

- `GET /api/review/proposals?status=open&limit=50`
  - Defaults to `status=open`
  - Supports `status=open|approved|rejected|all`
  - Returns reviewer-facing proposal fields: `id`, `target_section`, `proposed_content`, `proposal_type`, `confidence`, `reason`, `source_context`, `status`, `created_at`, `updated_at`, `reviewed_at`
- `POST /api/review/proposals/{proposal_id}/approve`
  - Runs existing approval workflow + semantic merge
  - Returns clear `ok` flag and updated proposal status payload
- `POST /api/review/proposals/{proposal_id}/reject`
  - Runs existing rejection workflow
  - Returns clear `ok` flag and updated proposal status payload
- `GET /api/review/digest-state?history_limit=10`
  - Returns latest persisted digest run state (`id`/run date, status, started/completed timestamps, error)
  - Also returns whether current local date already completed successfully
  - Includes recent `digest_run` history entries from event log when available
- `GET /api/review/memory`
  - Read-only inspection for current `core_profile.md` and `active_memory.md`
  - Exposes both raw content and section-extracted view for:
    - core: `About Her`, `Relationship Core`, `My Profile`
    - active: `Current Status`, `Purpose Context`, `On the Horizon`, `Others`

Known limitations:
- Surface is intentionally backend/debug-first and not a polished operator UI.
- Digest history is event-derived (best effort) and may be limited by event retention.
- TODO: add richer review pagination/filtering and explicit reviewer identity metadata.

## Human-like message segmentation
Feishu and QQBot outbound text now prefer newline-based segmentation. Each non-empty line is sent as an individual message segment, with a short configurable delay between segments, and long lines still fall back to chunking by `send_chunk_chars`.

## Privacy / sanitization
This OSS build excludes personal memories, private profiles, live API keys/tokens, and conversation logs. Use `data/config.example.json` as the template for local configuration; create your own untracked `data/config.json` when deploying.

## Trilium integration (Phase 1)
The gateway now includes a Trilium client module for deployment integration groundwork.

Environment variables:
- `TRILIUM_ENABLED`
- `TRILIUM_URL`
- `TRILIUM_ETAPI_TOKEN` (recommended)
- `TRILIUM_TOKEN` (backward-compatible fallback)
- `TRILIUM_TIMEOUT_SECONDS` (optional, default `10`)

Current client surface (`saki_gateway.trilium.TriliumClient`):
- `health_check()`
- `search_notes(query, limit=5, parent_note_id=None)`
- `get_note(note_id)`
- `get_note_content(note_id)`
- `list_children(parent_note_id)`

Behavior:
- Uses bounded request timeout.
- Returns safe fallbacks (`[]`, `None`, or `""`) when Trilium is down or unreachable.
- Avoids credential leakage by never exposing `TRILIUM_TOKEN` in public config payloads.


Phase 2 gateway tools are now available when Trilium is enabled and configured:
- `search_trilium`
- `get_trilium_note`

Routing rule in system prompt: for diary notes / study notes / book notes / "my notes", the model is instructed to call `search_trilium` first and then `get_trilium_note`.


## Manual E2E test case (Trilium read-only flow)
1. Set env vars and start gateway:
   - `TRILIUM_ENABLED=true`
   - `TRILIUM_URL=http://<your-trilium-host>`
   - `TRILIUM_ETAPI_TOKEN=<your-etapi-token>`
2. In chat, send: `帮我找一下我的学习笔记里关于线性代数的内容`
3. Confirm tool behavior in logs / tool events:
   - first `search_trilium` runs and injects only compact candidates (titles + ids)
   - then `get_trilium_note` runs for one selected note and injects truncated/compact content
4. Validate result distinction:
   - if Trilium is down/unreachable: assistant should indicate **Trilium unavailable**
   - if Trilium is healthy but query returns empty: assistant should indicate **no notes found**
5. Send an ordinary chat message like `今天心情有点低落` and confirm Trilium tools are not triggered unless notes are explicitly requested.


## Learning session foundation (Phase 4 next slice)
This slice adds a backend-first learning-session flow focused on sustainable study continuity (not harsh productivity scoring).

### Runtime SQLite schema
`runtime_store` now persists:

- `learning_sessions`
  - `id`, `title`, `goal`, `subject`, `mode`, `status`, `runtime_state`
  - `planned_minutes`, `pomodoro_count`, `elapsed_minutes`, `remaining_minutes`, `break_count`
  - `short_break_minutes`, `long_break_minutes`, `pause_started_at`
  - `started_at`, `ended_at`, `actual_minutes`, `summary`, `blockers`, `next_step`, `created_at`, `updated_at`
- `wellbeing_checkins`
  - `id`, `session_id`, `stage`, `energy_level`, `focus_level`, `mood_level`, `body_state_level`, `stress_level`, `note`, `created_at`
- `learning_session_events`
  - inspectable lifecycle/runtime events emitted by the backend
- `learning_session_responses`
  - queued proactive companion messages linked to learning events
- `learning_response_styles`
  - lightweight runtime response-style overrides (`default` or per-session scope)

Mode lifecycle:
- `focus | recovery | review`

Status lifecycle:
- `active -> completed`
- `active -> abandoned`

Runtime state lifecycle (minimal backend slice):
- `focus -> paused -> focus`
- `focus -> focus_completed -> break -> focus`
- terminal transitions force `completed` or `abandoned`

Guardrails:
- At most one `active` learning session at a time.
- State transitions require active status.
- `actual_minutes` is computed from `started_at`/`ended_at` when not provided.
- Very small `planned_minutes` values are allowed and `mode=recovery` is first-class.
- Invalid runtime transitions (for example resume without pause) are rejected.
- Study-mode responses stay short, non-sexual, and avoid degrading/punitive language.

### Minimal backend/admin endpoints
Authenticated dashboard API routes:

- `GET /api/learning-sessions/active`
- `GET /api/learning-sessions?status=&limit=20`
- `GET /api/learning-sessions/{session_id}`
- `GET /api/learning-sessions/{session_id}/checkins?limit=20`
- `POST /api/learning-sessions/start`
  - supports optional `start_checkin`
- `POST /api/learning-sessions/{session_id}/update`
- `POST /api/learning-sessions/{session_id}/runtime`
  - `action` supports `pause`, `resume`, `focus_completed`, `break_started`, `break_completed`, `paused_too_long`
- `POST /api/learning-sessions/{session_id}/complete`
  - supports optional `end_checkin`
- `POST /api/learning-sessions/{session_id}/abandon`
  - supports optional `end_checkin`
- `POST /api/learning-sessions/{session_id}/checkins`
- `GET /api/learning-sessions/{session_id}/events?limit=20`
- `GET /api/learning-sessions/{session_id}/responses?limit=20`
- `GET /api/learning-sessions/style?session_id=`
- `GET /api/learning-sessions/framework?session_id=`
- `POST /api/learning-sessions/style?session_id=`

### Check-in behavior
- `stage` supports `start | end`.
- Structured levels are lightweight (1-5) and optional.
- Short free-text `note` is supported.

### Event model and response generation flow
Supported event types in this slice:

- `session_started`
- `focus_completed`
- `break_started`
- `break_completed`
- `session_paused`
- `session_paused_too_long`
- `session_resumed`
- `session_completed`
- `session_abandoned`
- `low_energy_start`
- `recovery_completion`

Flow:
1. learning-session lifecycle or runtime control emits a lightweight event row
2. the event is mirrored into the existing gateway event log for debugging
3. the backend builds a short companion response from:
   - event type
   - session mode
   - recent wellbeing/check-in context if available
   - effective response-style config
   - layered persona-ready defaults
4. the response is stored in `learning_session_responses` with `delivery_status=queued`

This is intentionally backend-first so future chat insertion, banners, or notifications can reuse the same queue.

### Layered persona-ready architecture
This slice keeps the repository general by separating response shaping into simple layers instead of one giant prompt blob:

- `base_persona_slot`
  - current default: neutral companion support baseline
- `context_overlay_slot`
  - current default: mode-specific overlay such as `study_mode::focus`, `study_mode::recovery`, `study_mode::review`
- `event_response_style_slot`
  - derived from the active style config dimensions
- `safety_boundary_slot`
  - current default: study-safe boundary rules

Current implementation details:

- The framework uses safe default layer values only.
- No private/project-specific persona prompt content is embedded in code.
- Future persona injection can plug into the layer slots without rewriting the event system.
- `GET /api/learning-sessions/framework?session_id=` exposes the active default framework for inspection/debugging.

### Response-style config
Safe default style:

- `dominance_style=medium`
- `care_style=steady`
- `praise_style=warm`
- `correction_style=gentle`

Supported dimensions:

- `dominance_style`: `low | medium | high`
- `care_style`: `soft | steady | strict_care`
- `praise_style`: `restrained | warm | possessive_lite`
- `correction_style`: `gentle | firm`

Notes:
- Style is runtime/config behavior, not long-term identity memory.
- Study mode does **not** automatically use sexual, intimate, or RP language.
- When wellbeing suggests exhaustion, anxiety, or physical strain, responses shift toward stabilization and smaller next steps.
- The current framework is persona-ready but not persona-customized yet.

### Minimal memory/digest-adjacent integration
- On completion, a concise long-term memory item is upserted with category `learning_session`.
- This allows the existing active-memory renderer to surface recent session outcomes with minimal change.
- No automatic `core_profile` mutation is performed.

Known limitations / TODO:
- No polished timer/dashboard UI in this slice.
- Responses are queued for inspection/future delivery, not yet inserted directly into the main chat timeline.
- No advanced wellbeing analytics or scoring.
- Mode overlays are lightweight defaults only; richer custom persona overlays are a future step.
- TODO: optional Trilium completion note output can be added later if needed.
- TODO: hook the queued responses into a future web notification/chat insertion surface.
- TODO: add a clean custom persona injection path that fills the existing layer slots without coupling everything to one prompt blob.
