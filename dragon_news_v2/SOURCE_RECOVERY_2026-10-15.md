# SHADOW-only source recovery — 2026-10-15

## Fixes

- Kommersant RSS: https://www.kommersant.ru/rss/main.xml (previous endpoint returned HTTP 301).
- Gazeta.Ru RSS: https://www.gazeta.ru/export/rss/first.xml (previous endpoint returned HTTP 404).
- RBC: https://t.me/s/rbc_news, publicly readable official Telegram channel replacing an RSS that external monitors show is unhealthy.
- Redirects: same-host HTTPS only, at most two hops, never a cross-host or HTTP downgrade.
- Network: at most one retry for transient connection/read timeout, no retries for 404 or 429.
- Inspect status using python shadow_runner.py --sources (read-only).

External monitoring suggests these URLs, but live reachability **from BotHost** is not established until the corrected collector runs on BotHost.

## Safe update (TEST BOT ONLY)

1. Open BotHost project **Dragon News 2.0 SHADOW**, never the production bot.
2. In repository/deployment settings select branch: **trial/dragon-news-v2-sources-20261015**.
3. Ensure main file remains **shadow_runner.py**, NOT main.py. Stop if this differs.
4. Use the existing separate test project's persistent /app/data volume. Never delete or replace dragon_news_shadow.sqlite3 or its WAL/SHM files.
5. Do not modify working BotHost project, production main, AUTO_SEND, token, or /app/data/dragon_news.sqlite3.
6. Deploy/restart **only SHADOW**, after verifying the above settings.

## Verify after restart (SHADOW terminal)

Run: python shadow_runner.py --status
Run: python shadow_runner.py --sources

These deliberately contain no command separators; the BotHost terminal may block semicolons even inside Python code.
All three repaired sources should appear with the new endpoints. Confirm each eventually shows a new last_success_at and last_error=null. Otherwise, collect source-specific errors, do not claim 12/12.
Check article count before/after: older publications are preserved because registry source IDs remain stable.

Seven-day quality assessment must use a stable interval after the update; previous partial cycles are useful historical diagnostics but do not certify corrected operation.
CI validates offline logic; it does not verify real RSS reachability from BotHost.
