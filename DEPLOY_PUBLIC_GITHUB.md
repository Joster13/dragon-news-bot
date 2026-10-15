# Dragon News: public GitHub + BotHost checklist

## 1. Create a PUBLIC repository

Open <https://github.com/new>, set repository name `dragon-news-bot`, visibility **Public**, and initialize with README (for easy GitHub-connected uploads). Keep the default branch `main`.

## 2. What is allowed in the repository

Commit Python source (`*.py`), `requirements.txt`, `README.md`, `.gitignore`, `.env.example`, `tests/`, and this checklist.

**Never commit:** a filled `.env`, Telegram token, OpenAI API key, private keys, database files, client messages or credentials. BotHost settings and tokens are **not** stored in the Git repository. A `.gitignore` only protects untracked files; it cannot undo a leaked commit.

## 3. BotHost configuration

Follow <https://bothost.ru/docs/getting-started> and <https://bothost.ru/docs/environment-variables>.

- Platform: **Telegram**; runtime: **Python**
- Git URL: `https://github.com/YOUR_LOGIN/dragon-news-bot.git`
- Branch: `main`
- Entry point: `main.py`
- Bot token: add the token obtained from @BotFather in BotHost's bot creation form; BotHost normally exposes it as `BOT_TOKEN` automatically

**Environment variables** (BotHost → bot → Settings → Environment variables):

| Name | Example value | Secret? |
|---|---|---|
| `ADMIN_ID` | YOUR_NUMERIC_TELEGRAM_ID | No, but don't publish unnecessarily |
| `NEWS_TZ` | `Europe/Moscow` | No |
| `NEWS_HOUR` | `9` | No |
| `NEWS_MINUTE` | `0` | No |
| `AUTO_SEND` | `true` | No |
| `MAX_ITEMS` | `28` | No |
| `DB_PATH` | `/app/data/dragon_news.sqlite3` | No |
| `OPENAI_API_KEY` | your actual key, if used | **YES** |
| `OPENAI_MODEL` | `gpt-4.1-mini` | No |

`BOT_TOKEN` is a **secret**, even if BotHost injects it automatically. Never put a real token in GitHub, README or screenshots.

To find your Telegram ID, start the bot and send `/id`, then fill `ADMIN_ID` and restart.

## 4. Test

Send `/demo`, `/status`, `/today`, and `/rates` in the private chat with the bot. For reliable automatic 09:00 delivery, the application must run continuously, and the database file must persist through redeployments.

Remember: the standalone bot pulls from RSS; it does *not* automatically receive the separate ChatGPT scheduled task's output.
