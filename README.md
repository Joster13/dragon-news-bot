# 🐉 Dragon News — Telegram Rich Messages News Bot

**A personal Telegram bot with a public-code friendly setup using `sendRichMessage` (Bot API 10.2+)**. New Telegram Rich Text Editor look: headings, separators, expandable news sections, internal tables, source links. Daily delivery at 09:00 Moscow time.

## What actually works

- `/demo`: visually rich mock report with expandable sections and a table.
- `/today`: automatically gathers news *published during the last ~27 hours* from Google News RSS searches, deduplicates with SQLite, and sends one rich report per day; no recycled old headlines.
- Separate priority section: **Липецк и Липецкая область**. Russia, laws, blocks/VPN, finances/USDT, SVO (RU/UA/Western queries), world, AI/IT/security, PC games.
- `/export`: export last report to editable `.md` file.
- `/rates`: a real PNG chart of official USD, EUR and CNY rates over the last several days, fetched from the Central Bank of Russia XML endpoint. No guessed market numbers.
- `/publish <markdown>` or send `.md`/`.txt` document: publish your own **finished ChatGPT digest** directly as Telegram Rich Message. Enables articles authored outside the bot to be delivered beautifully.
- `/poll Вопрос | Вариант 1 | Вариант 2`: real Telegram poll, *separate from Rich Message*.
- If `OPENAI_API_KEY` is set, generates careful short Russian explanations strictly from RSS titles/snippets (paid API usage). Without it, works for free using RSS excerpts and section-specific context.
- Only an `ADMIN_ID` can read/publish/manage the bot; timestamps checked, persistent SQLite history, source links, Telegram API fallback when a rich message is rejected.

### Limits / important accuracy notice

- This is an **independent** BotHost app. Your ChatGPT scheduled news task cannot automatically be intercepted or forwarded to this bot. To send the exact text, use `/publish` or upload a `.md` file. To automate article writing fully, use RSS + optional AI key.
- Free RSS mode gives headlines and excerpts, **not** the same quality of verification as a manually researched ChatGPT briefing. AI mode improves prose but cannot independently verify claims from an RSS headline. Important legal/military claims should be checked in the linked original. Google News feed item links sometimes first go through Google News instead of directly to the publisher.
- Some news feed items have only a title. The bot says so instead of inventing details. Articles without a timestamp are excluded.
- RSS availability and reachability depend on the hosting location. The bot refuses to claim it gathered news if fewer than three source queries work.
- `/today` and the daily schedule share a one-per-day anti-duplication rule. No duplicate digest will be sent on the same Moscow date; `/export` re-sends the saved text.
- Rich messages support up to 32,768 characters and multiple blocks. Oversized reports are split into smaller parts.
- Polls are sent as standalone messages via `sendPoll`; if you want real interactive charts, this requires verified numerical datasets + chart image generation or a Telegram Mini App. Never invent exchange rates / graphs.

## Deploy to BotHost

1. Telegram: message **@BotFather**, run `/newbot`, choose a name and username, copy `BOT_TOKEN`. Never paste it into GitHub or a public chat.
2. Publish **only source files** to a **public GitHub repository** (e.g. `yourname/dragon-news-bot`). The included `.env.example` contains no credentials; real secrets must never be committed. The `.gitignore` excludes local `.env*` (except `.env.example`), SQLite data, logs, private keys and Python caches.
3. Go to **https://bothost.ru/dashboard.php** → Create Telegram bot, Python, entrypoint **`main.py`**, and provide a public Git URL such as `https://github.com/yourname/dragon-news-bot.git`, branch `main`. **No GitHub access token is needed for a public repository.** BotHost normally injects `BOT_TOKEN` from the Telegram bot form; otherwise enter it securely in environment variables.
4. In BotHost → bot settings → **Environment variables**, configure non-secret scheduling values and `ADMIN_ID`. To learn it you may first boot without `ADMIN_ID`, send `/id` from your private Telegram chat, then put your **numeric** Telegram ID into `ADMIN_ID` and restart. Never use a username or BotHost's `USER_ID` in place of numeric Telegram ID.
5. Set `DB_PATH=/app/data/dragon_news.sqlite3`, `NEWS_TZ=Europe/Moscow`, `NEWS_HOUR=9`, `NEWS_MINUTE=0`. Use BotHost's persistent `/app/data` volume for history retention.
6. Send `/start`, then `/demo`, and `/today` to preview a real auto-collected digest. Optionally set `OPENAI_API_KEY` **in BotHost environment variables only** (API usage is charged) and `OPENAI_MODEL`. Do **not** share keys in GitHub issues, commits, screenshots or chats.
7. For reliable daily delivery choose a **24/7 plan** (e.g. BotHost Active). A sleeping free plan may not run the 09:00 timer. A VPS also works with systemd.

The scheduler catches up if it starts *after* 09:00 on a day with no earlier delivery; it is guarded by a date key in SQLite.

## Local install

Python 3.11 or newer:

```bash
python -m venv .venv
.venv/Scripts/activate # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env     # on Windows: copy .env.example .env
# Edit BOT_TOKEN, ADMIN_ID and DB_PATH=./data/dragon_news.sqlite3
python main.py
```

To run unit tests:

```bash
python -m unittest discover -s tests -v
```

## Security

- The bot stores previously sent news identifiers and last published Markdown in SQLite; it does not store login passwords or bank data.
- Only your numeric Telegram ID is authorized for sending, viewing and exporting the report.
- **Public GitHub is safe for source code, not secrets.** Keep `BOT_TOKEN`, `OPENAI_API_KEY` and any future provider credentials exclusively in BotHost environment variables; `.env` is for local use and must not be committed.
- `.gitignore` does not erase already-committed secrets. If a token ever enters a public commit, **revoke/rotate it immediately** in @BotFather or your API provider; removing it in a later commit is not sufficient.
- BotHost automatically supplies `BOT_TOKEN` when the bot token is entered during bot creation; `ADMIN_ID` is the Telegram numeric ID, not the BotHost `USER_ID`.
- For sensitive news, links and timestamps are not a substitute for independent verification.
- If you rotate the bot token, update BotHost environment and restart.

## Sources and API

Official Telegram: https://telegram.org/blog/communities-editor-invisible-messages and https://core.telegram.org/bots/api#rich-messages

BotHost documentation: https://bothost.ru/docs/getting-started and https://bothost.ru/docs/


## Dragon News 2.0 — shadow collector (experimental)

This feature exists only in the draft feature branch. Creating a PR does not deploy it.
The legacy Telegram commands, Rich Messages and 09:00 Moscow scheduler are unchanged.

- V2_SHADOW_ENABLED=false (default): no shadow database opens and no collector starts.
- V2_SHADOW_ENABLED=true: an hourly collector runs inside the existing bot process and uses its HTTP client; no second Telegram poller.
- V2_DB_PATH=/app/data/dragon_news_shadow.sqlite3: a separate SQLite file; the integration rejects production DB_PATH.

Shadow mode now collects hourly and writes a **daily local-only test digest at 09:00 Moscow**
(with incomplete-report catch-up allowed before 12:00); it **does not send Telegram messages**.
Reports, audit decisions and HTML previews stay in the separate shadow SQLite.
The operator elected to skip the production DB backup, knowingly accepting loss risk.
Therefore do not migrate, overwrite or access the live /app/data/dragon_news.sqlite3.
A backup is strongly recommended before any future migration/deployment, and GitHub
cannot back up the BotHost /app/data disk.
Never commit tokens, SQLite databases or private data to this public repository.
Do not merge this draft PR or alter the active AUTO_SEND setting without an explicit release decision.

Offline checks: python -m compileall -q . ; python -m unittest discover -s tests -v.
Real feed reachability must be tested later from the BotHost network.
