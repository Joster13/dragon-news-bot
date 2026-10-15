# Dragon News 2.0: seven-day isolated BotHost shadow trial

## Safety boundary

**DO NOT redeploy the existing Dragon News BotHost project.**
Create an entirely separate project/instance with its own BotHost data volume.

- Git repository: https://github.com/Joster13/dragon-news-bot.git
- Branch: \`feature/dragon-news-v2-shadow-7day\` (or an explicitly frozen copy of this tested commit).
- Advanced settings / Main File / Entry Point: \`shadow_runner.py\`, **not** \`main.py\`.
- SQLite: \`/app/data/dragon_news_shadow.sqlite3\` in the **new**, isolated project/container.
- No credentials, Telegram polling, webhooks or Telegram sends are performed by the entrypoint.
- If BotHost requires a bot token during project creation, create a **separate test bot** with BotFather; do **not** reuse the production bot token. The shadow code ignores the token.
- Do not share the live BotHost data directory, mount or database with this project.
- Do not change production \`AUTO_SEND\`, \`DB_PATH\`, \`main\` branch, \`main.py\`, token, or live project configuration.
- The operator chose to skip the live database backup, accepting the data loss risk. This trial makes **no migration or write** to the live DB.

## Preconditions

1. Confirm a second independently deployed BotHost project/slot is available. A trial in the existing project is not an equivalent safe alternative.
2. Confirm the new project runs uninterrupted around 09:00 MSK; a sleeping plan cannot give meaningful hourly coverage.
3. Ensure Python >=3.11 and \`requirements.txt\` installed.
4. Verify deployment logs show the standalone shadow runner and no Telegram \`getUpdates\` operations. If logs indicate \`main.py\`, STOP and check Main File.
5. First deployment is observation only; do not switch automatic deployment on the working project.
6. Confirm \`/app/data\` in the new project is not shared with the production project.

Official BotHost guides:
- https://bothost.ru/docs/repository-branch-deploy
- https://bothost.ru/docs/main-file-entrypoint
- https://bothost.ru/docs/database-storage
- https://bothost.ru/docs/sqlite-terminal

## Timeline

Hourly: fetch RSS, Atom, public Telegram publications to the isolated SQLite.
09:00 MSK: evaluate and save one test digest for the prior editorial day.
09:00–12:00 MSK: an incomplete local-only digest may be recovered if sources return.
After 12:00 MSK: no late automatic digest creation for that day.
After seven days: manually inspect the report and stop the second project; the runner does not automatically stop itself.

The operational timer alone **does not** certify editorial quality. Target evaluation:
- At least 60 real source-linked articles manually labelled for relevance and importance;
- At least 95% topical precision and 85% recall on the labelled dataset;
- No critical mistaken merges, fabricated facts, missing attribution or missing source URLs;
- Seven operational days with useful source coverage, with all partial and failed polls audited.
Report precision/recall as *unmeasured* until labels exist; do not substitute synthetic unit tests.

## Monitoring (run only in the TEST project terminal)

Read-only summary, does not create/modify SQLite:
\`\`\`sh
python shadow_runner.py --status
\`\`\`

Read one day's selected news in JSON, without sending to Telegram:
\`\`\`sh
python shadow_runner.py --preview-date 2026-10-16
\`\`\`

The date is illustrative: substitute a real day of the seven-day trial.
Use these commands in the test project's terminal, NOT the production project.

Key fields:
- \`status\`: \`collecting\`, \`needs_attention\`, or \`ready_for_review\`;
- \`collector_runs\`, \`successful_collections\`, \`partial_collections\`, \`failed_collections\`;
- \`completed_days\`, \`days_seen\`, \`missing_days\`, \`incomplete_days\`;
- \`ready_for_review\` means only that the operational seven-day timeline was collected;
- \`quality_review_complete: false\`, \`precision: null\`, \`recall: null\` until manual annotation.

## Abort / rollback

Stop **only the test project** if:
- Logs show unexpected Telegram polling or interactions with the live DB;
- BotHost is running \`main.py\` rather than \`shadow_runner.py\`;
- Path guard fails, frequent SQL errors, or sources are consistently unavailable.

Stopping the test project does not require changing the active bot. No automatic production rollback, merge or deployment is part of this trial.

## Known gaps

- Manual review of 60+ real news stories is not automated.
- External source availability and uptime remain unverified until the trial runs on BotHost.
- The program does not call a paid AI API.
- If a separate BotHost project is unavailable, do not redeploy the active bot. Discuss a safer alternative before proceeding.
