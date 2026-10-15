# Dragon News 2.0 — Stage 2 editorial modules (draft)

Stage 2 is currently **offline-only**. This branch must not be merged or deployed as the production digest.

## Modules

- `matcher.py`: deterministic, conservative grouping of Articles; 'possible' never merges; distinguish legislative readings, decisions, bill IDs and CVE products.
- `evidence.py`: statement origin roots and explainable `official_statement`, `multi_independent`, `single_attributed`, `disputed`, `insufficient`. Independent roots must be explicitly identified via `origin_map`; two press-release rewrites count as one, unknown roots never create fake corroboration.
- `editor.py`: 24-hour window ending at the supplied Moscow cutoff, existing relevance filters, dynamic topic priority, no artificial padding.
- `builder.py`: immutable day-specific digest snapshots with deterministic hash and source-grounded excerpts.
- `legacy_bridge.py`: escaped Telegram Rich HTML and <=3200-character fallback chunks, without modifying legacy rendering.

## Boundaries and release blockers

1. The opt-in v2 hourly collector now connects to the editorial pipeline and saves daily 09:00 Moscow shadow snapshots, evidence states, event-article links and decision reasons in the separate v2 SQLite database. An INCOMPLETE shadow snapshot can be refreshed before 12:00; no Telegram message is sent. This is covered by offline regression tests, **not** a completed 7-day live shadow trial.
2. The 60+ real, manually labelled, source-linked test corpus required by the approved plan **has not been collected or measured**. Existing regression titles and synthetic tests are not a substitute for real-world precision and recall. Target: >=95% topical precision, >=85% recall.
3. The current origin_map must come from explicit provenance analysis; unknown origin is conservatively treated as unverified. Do not derive independent roots merely from different publisher names.
4. CI checks are offline: they do not verify that each RSS/Telegram site responds from BotHost.
5. Production database `/app/data/dragon_news.sqlite3` must not be accessed by v2; the operator elected to skip a production DB backup, so no migration, merge, or deployment is permitted without a separate release decision.
6. No paid AI API or second Telegram poller is used.

## Verification

```sh
python -m compileall -q .
python -m unittest discover -s tests -v
```

Scope: module-level correctness tests only; keep the PR draft. 
