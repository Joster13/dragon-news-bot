"""Dragon News: private Telegram news bot with Bot API Rich Messages.

Hosted in a single long-running Python process (BotHost Active plan or VPS).
Set BOT_TOKEN, ADMIN_ID, then python main.py.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

from ai import explain_with_ai
from finance import chart_png, fetch_cbr_history, SOURCE_URL
from news import NewsItem
from direct_news import collect_news, enrich_optional, source_report
from rendering import export_markdown, fallback_html, rich_html
from storage import Storage
from selfcheck import BUILD_ID, run_selfcheck

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# httpx INFO logs include the full Telegram API URL, which embeds BOT_TOKEN.
# Suppress third-party request logging while retaining application diagnostics.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("dragon-news")

TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
ADMIN_ID = int(os.getenv("ADMIN_ID") or "0")
TZ = ZoneInfo(os.getenv("NEWS_TZ", "Europe/Moscow"))
HOUR = int(os.getenv("NEWS_HOUR", "9"))
MINUTE = int(os.getenv("NEWS_MINUTE", "0"))
MAX_ITEMS = max(1, min(30, int(os.getenv("MAX_ITEMS", "28"))))
AUTO_SEND = os.getenv("AUTO_SEND", "true").lower() == "true"
DB_PATH = os.getenv("DB_PATH", "./data/dragon_news.sqlite3")


class BotAPIError(Exception):
    def __init__(self, method: str, status: int, detail: str):
        super().__init__(f"Telegram {method}: {status} {detail[:350]}")
        self.status = status


class NewsBot:
    def __init__(self):
        self.db = Storage(DB_PATH)
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=12.0),
                                       headers={"User-Agent": "DragonNewsBot/1.0 (+RSS personal briefing)"},
                                       follow_redirects=True)
        self.lock = asyncio.Lock()
        self.last_attempt = None
        self.preview_task = None
        self.preview_busy_notice = False

    async def api(self, method: str, payload: dict | None = None, files: dict | None = None):
        target = f"https://api.telegram.org/bot{TOKEN}/{method}"
        if files:
            response = await self.client.post(target, data=payload, files=files, timeout=40)
        else:
            response = await self.client.post(target, json=payload or {}, timeout=45)
        try:
            data = response.json()
        except ValueError as ex:
            raise BotAPIError(method, response.status_code, "Invalid API response") from ex
        if not response.is_success or not data.get("ok"):
            raise BotAPIError(method, response.status_code, data.get("description", "Unknown error"))
        return data["result"]

    async def text(self, chat_id: int, value: str, **extra):
        return await self.api("sendMessage", {"chat_id": chat_id, "text": value, **extra})

    async def send_rich(self, chat_id: int, markup: str, plain_fallback: list[str], keyboard=None):
        """Use real 2026 rich message API. Fall back on old clients/API failures (400)."""
        args = {"chat_id": chat_id, "rich_message": {"html": markup}}
        if keyboard:
            args["reply_markup"] = keyboard
        try:
            return await self.api("sendRichMessage", args)
        except BotAPIError as ex:
            if ex.status != 400 and ex.status != 404:
                raise
            log.warning("Rich message rejected (%s), using regular HTML", ex)
            message = None
            for i, chunk in enumerate(plain_fallback):
                message = await self.text(chat_id, chunk, parse_mode="HTML",
                                          disable_web_page_preview=True,
                                          **({"reply_markup": keyboard} if i == len(plain_fallback) - 1 and keyboard else {}))
            return message

    async def digest(self, manual: bool = False):
        if not ADMIN_ID:
            log.error("ADMIN_ID not configured; unable to send a digest")
            return False
        async with self.lock:
            now = datetime.now(TZ)
            day = now.date().isoformat()
            if self.db.has_delivered(day):
                if manual:
                    await self.text(ADMIN_ID, "Сводка на сегодня уже отправлена. Используй /export для копии.")
                return False
            self.last_attempt = now
            log.info("Gathering dated news for %s", day)
            fresh, sources_available = await collect_news(
                self.client, now, self.db.seen(), MAX_ITEMS,
                recent_events=self.db.recent_events()
            )
            fresh = await enrich_optional(self.client, fresh)
            if sources_available < 1:
                if self.db.setting("rss_error_notice_day") != day:
                    await self.text(ADMIN_ID, "Не удалось подключиться к достаточному количеству новостных лент. "
                                              "Не подменяю свежие новости старой информацией. Попробуй /today позже.")
                    self.db.put_setting("rss_error_notice_day", day)
                return False
            if not fresh:
                await self.text(ADMIN_ID, "DRAGON NEWS · " + now.strftime("%d.%m.%Y") +
                                          "\nЗа сутки не найдено новых публикаций, отвечающих правилам отбора. "
                                          "Старые новости не повторяю.")
                self.db.record(day, "Новых публикаций не обнаружено.", [])
                return True
            summary_map = await explain_with_ai(self.client, fresh)
            # html representation has more markup than visible characters.
            rendered = rich_html(fresh, now, summary_map)
            if len(rendered.encode("utf-8")) > 58000 or len(rendered) > 31000:
                # Never truncate sources or paragraphs. Split the digest into two chunks.
                chunks = [fresh[:len(fresh)//2], fresh[len(fresh)//2:]]
            else:
                chunks = [fresh]
            keyboard = {"inline_keyboard": [[
                {"text": "Статус", "callback_data": "status"},
                {"text": "Экспорт .md", "callback_data": "export"}
            ]]}
            for idx, article_slice in enumerate(chunks):
                rendered_chunk = rich_html(article_slice, now, summary_map)
                await self.send_rich(ADMIN_ID, rendered_chunk, fallback_html(article_slice, now),
                                     keyboard if idx == len(chunks) - 1 else None)
            self.db.record(day, export_markdown(fresh, now), [a.key for a in fresh], articles=fresh)
            log.info("Digest delivered for %s: %s items", day, len(fresh))
            return True

    async def preview(self, chat_id: int):
        """Run a bounded preview in the background so Telegram polling stays responsive."""
        try:
            async with self.lock:
                now = datetime.now(TZ)
                log.info("Preview started for %s", now.date())
                fresh, sources_available = await asyncio.wait_for(
                    collect_news(self.client, now, set(), min(MAX_ITEMS, 28)), timeout=58
                )
                fresh = await asyncio.wait_for(enrich_optional(self.client, fresh), timeout=35)
                if sources_available < 3:
                    await self.text(chat_id, "Не удалось получить новости: доступны менее трёх RSS-лент. Попробуй позже.")
                elif not fresh:
                    await self.text(chat_id, "Свежих публикаций для предпросмотра пока нет.")
                else:
                    summaries = await asyncio.wait_for(explain_with_ai(self.client, fresh), timeout=32)
                    await self.send_rich(chat_id, rich_html(fresh, now, summaries), fallback_html(fresh, now))
                    log.info("Preview delivered: %s articles", len(fresh))
        except asyncio.TimeoutError:
            log.warning("Preview timed out")
            await self.text(chat_id, "Сбор новостей превысил лимит времени. RSS или AI не отвечают. Попробуй /preview позже.")
        except Exception:
            log.exception("Preview failed")
            try:
                await self.text(chat_id, "Ошибка подготовки предпросмотра. Подробности в логах BotHost (без токенов).")
            except Exception:
                log.exception("Could not send preview failure notice")
        finally:
            self.preview_task = None
            self.preview_busy_notice = False

    async def export(self, chat_id: int):
        last = self.db.last()
        if not last:
            await self.text(chat_id, "Пока нет сохранённой сводки.")
            return
        day, _, markdown = last
        await self.api("sendDocument", {"chat_id": chat_id, "caption": f"DRAGON NEWS · {day}"},
                       files={"document": (f"dragon_news_{day}.md", markdown.encode("utf-8"), "text/markdown")})

    async def rates(self, chat_id: int):
        now = datetime.now(TZ)
        data = await fetch_cbr_history(self.client, now.date())
        if len(data) < 2:
            await self.text(chat_id, "Не получилось получить достоверные исторические курсы ЦБ. График без данных не строю.")
            return
        png = chart_png(data)
        last_day, values = data[-1]
        caption = (f"Официальные курсы ЦБ на {last_day.strftime('%d.%m.%Y')}\n"
                   + " | ".join(f"{k}: {values[k]:.4f} ₽" for k in ("USD", "EUR", "CNY"))
                   + f"\nИсточник: {SOURCE_URL}")
        await self.api("sendPhoto", {"chat_id": chat_id, "caption": caption},
                       files={"photo": ("cbr_rates.png", png, "image/png")})

    async def handle_message(self, msg: dict):
        user = msg.get("from", {})
        user_id = int(user.get("id", 0))
        chat_id = int(msg.get("chat", {}).get("id", 0))
        text = msg.get("text", "")
        command = text.split(None, 1)[0].split("@")[0].lower() if text.startswith("/") else ""

        if command == "/id":
            await self.text(chat_id, f"Твой Telegram ID: {user_id}\nВ настройках хостинга задай ADMIN_ID={user_id}.")
            return
        if not ADMIN_ID:
            await self.text(chat_id, "Бот ещё не привязан к владельцу. Напиши /id, "
                                      "а затем укажи полученный ID в ADMIN_ID на хостинге.")
            return
        if user_id != ADMIN_ID or chat_id != ADMIN_ID:
            # Do not disclose news, schedule, sources, or settings to other users.
            return
        if command in ("/start", "/help"):
            await self.text(chat_id, "🐉 DRAGON NEWS · личный дайджест\n\n"
                             f"Автоматически каждый день в {HOUR:02d}:{MINUTE:02d} МСК.\n"
                             "/today — отправить свежую сводку сейчас (один раз в день)\n"
                             "/preview — проверить новости без записи в историю\n"
                             "/sources — проверить доступность источников\n"\n                             "/selftest — версия и проверка редакционных фильтров\n"
                             "/demo — посмотреть новый формат Rich Messages\n"
                             "/export — получить предыдущую сводку .md\n"
                             "/rates — график USD / EUR / CNY по данным ЦБ\n"
                             "/status — статус отправки и расписания\n"
                             "/publish текст — вручную опубликовать готовый Markdown\n"
                             "/poll Вопрос | Вариант 1 | Вариант 2 — опрос\n"
                             "Можно отправить .md-файл: бот опубликует его как Rich Message.")
        elif command == "/status":
            last = self.db.last()
            await self.text(chat_id, f"Расписание: ежедневно {HOUR:02d}:{MINUTE:02d} МСК\n"
                             f"Автоотправка: {'включена' if AUTO_SEND else 'выключена'}\n"
                             f"Последняя отправка: {last[0] if last else 'ещё нет'}\n"
                             f"Сборка: {BUILD_ID}\n"
                             f"OpenAI API: {'подключён' if os.getenv('OPENAI_API_KEY') else 'не подключён (RSS-режим)'}")
        elif command == "/today":
            await self.digest(manual=True)
        elif command == "/sources":
            await self.text(chat_id, source_report())
        elif command == "/selftest":
            await self.text(chat_id, run_selfcheck())
        elif command == "/preview":
            if self.preview_task is not None and not self.preview_task.done():
                if not self.preview_busy_notice:
                    await self.text(chat_id, "Предпросмотр уже формируется. Дождись результата, повторные команды не нужны.")
                    self.preview_busy_notice = True
            else:
                await self.text(chat_id, "Собираю свежие новости. Обычно это занимает до минуты; не отправляй команду повторно.")
                self.preview_task = asyncio.create_task(self.preview(chat_id))
        elif command == "/export":
            await self.export(chat_id)
        elif command == "/rates":
            await self.rates(chat_id)
        elif command == "/demo":
            # Demonstration explicitly fictional, not a news claim.
            rich = ('<h1>🐉 DRAGON NEWS · ДЕМО</h1><p>Пример дизайна; все новости ниже — вымышленные.</p>'
                    '<hr/><details open><summary><b>Липецк и область</b></summary>'
                    '<h3>Пример новости о ремонте дороги</h3>'
                    '<p>Здесь будет: что случилось, точные сроки, адреса, последствия.</p>'
                    '<p><b>Источник:</b> ссылка на конкретную публикацию.</p></details>'
                    '<details><summary><b>Финансы и законы</b></summary>'
                    '<p>Сворачиваемый раздел, чтобы не перегружать сообщение.</p></details>'
                    '<table bordered striped compact><tr><th>Тема</th><th>Пунктов</th></tr>'
                    '<tr><td>Липецк</td><td>3 (пример)</td></tr>'
                    '<tr><td>IT</td><td>2 (пример)</td></tr></table>'
                    '<footer>В боевых сообщениях только новости с датами и источниками.</footer>')
            fallback = ['<b>DRAGON NEWS · ДЕМО</b>\n'
                        'Липецк и область\nПример новости о дороге.\n'
                        'Финансы и законы\nЭто макет, без реальных событий.']
            await self.send_rich(chat_id, rich, fallback)
        elif command == "/publish":
            body = text.partition(" ")[2].strip()
            if not body:
                await self.text(chat_id, "Пришли /publish и Markdown-текст в том же сообщении или загрузи .md файл.")
            elif len(body) > 30000:
                await self.text(chat_id, "Текст слишком длинный: максимум около 30 000 символов.")
            else:
                await self.api("sendRichMessage", {"chat_id": chat_id, "rich_message": {"markdown": body}})
        elif command == "/poll":
            parts = [x.strip() for x in text.partition(" ")[2].split("|") if x.strip()]
            if len(parts) < 3 or len(parts) > 11:
                await self.text(chat_id, "Формат: /poll Вопрос | Ответ 1 | Ответ 2 [| ... до 10 ответов]")
            else:
                await self.api("sendPoll", {"chat_id": chat_id, "question": parts[0][:300],
                                            "options": [{"text": a[:100]} for a in parts[1:]],
                                            "is_anonymous": False})
        elif "document" in msg:
            doc = msg["document"]
            filename = doc.get("file_name", "").lower()
            if not filename.endswith((".md", ".txt")) or doc.get("file_size", 0) > 70000:
                await self.text(chat_id, "Поддерживаются только .md/.txt файлы размером до 70 КБ.")
                return
            meta = await self.api("getFile", {"file_id": doc["file_id"]})
            path = meta.get("file_path", "")
            if not path:
                return
            response = await self.client.get(f"https://api.telegram.org/file/bot{TOKEN}/{path}", timeout=25)
            response.raise_for_status()
            data = response.content.decode("utf-8-sig")
            if len(data) > 32000:
                await self.text(chat_id, "Markdown превышает лимит Rich Messages. Раздели файл на две части.")
            else:
                await self.api("sendRichMessage", {"chat_id": chat_id, "rich_message": {"markdown": data}})

    async def handle_callback(self, query: dict):
        data = query.get("data")
        who = int(query.get("from", {}).get("id", 0))
        await self.api("answerCallbackQuery", {"callback_query_id": query["id"]})
        if who != ADMIN_ID:
            return
        if data == "status":
            last = self.db.last()
            await self.text(ADMIN_ID, f"Последняя сводка: {last[0] if last else 'ещё не было'}; каждый день в {HOUR:02d}:{MINUTE:02d} МСК")
        if data == "export":
            await self.export(ADMIN_ID)

    async def listen(self):
        offset = int(self.db.setting("offset", "0"))
        while True:
            try:
                updates = await self.api("getUpdates", {"offset": offset, "timeout": 25,
                                                         "allowed_updates": ["message", "callback_query"]})
                for upd in updates:
                    offset = max(offset, int(upd["update_id"]) + 1)
                    self.db.put_setting("offset", str(offset))
                    try:
                        if "message" in upd:
                            await self.handle_message(upd["message"])
                        elif "callback_query" in upd:
                            await self.handle_callback(upd["callback_query"])
                    except Exception:
                        log.exception("Error handling update %s", upd["update_id"])
            except asyncio.CancelledError:
                raise
            except (httpx.HTTPError, BotAPIError):
                log.exception("Telegram polling failed; retrying")
                await asyncio.sleep(7)

    async def scheduler(self):
        while True:
            now = datetime.now(TZ)
            if AUTO_SEND and (now.hour, now.minute) >= (HOUR, MINUTE):
                retry_ok = self.last_attempt is None or now - self.last_attempt > timedelta(minutes=30)
                if retry_ok and not self.db.has_delivered(now.date().isoformat()):
                    try:
                        await self.digest()
                    except Exception:
                        log.exception("Scheduled digest failed")
            await asyncio.sleep(45)

    async def run(self):
        # getUpdates and webhook are mutually exclusive. This instance uses polling.
        await self.api("deleteWebhook", {"drop_pending_updates": False})
        await self.api("setMyCommands", {"commands": [
            {"command": "start", "description": "Меню"},
            {"command": "today", "description": "Новости на сегодня"},
            {"command": "demo", "description": "Посмотреть Rich Messages"},
            {"command": "sources", "description": "Источники новостей"},
            {"command": "selftest", "description": "Проверка версии и фильтров"},
            {"command": "status", "description": "Расписание и состояние"},
            {"command": "export", "description": "Сводка в Markdown"},
            {"command": "rates", "description": "График валют ЦБ РФ"},
        ]})
        log.info("Dragon News running build=%s (ADMIN_ID configured: %s)", BUILD_ID, bool(ADMIN_ID))
        try:
            await asyncio.gather(self.listen(), self.scheduler())
        finally:
            await self.client.aclose()


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("BOT_TOKEN missing. Create a Telegram bot in @BotFather.")
    asyncio.run(NewsBot().run())
