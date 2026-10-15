"""Optional constrained explanation with OpenAI API; never fabricate facts."""
import json
import logging
import os

import httpx
from news import NewsItem, IMPACT

log = logging.getLogger(__name__)


async def explain_with_ai(client: httpx.AsyncClient, items: list[NewsItem]) -> dict[str, tuple[str, str]]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key or not items:
        return {}
    # Only public RSS titles/snippets/links are transmitted to model API.
    data = [{"id": n.key, "topic": n.topic, "title": n.title,
             "excerpt": n.summary, "source": n.source, "viewpoint": n.viewpoint}
            for n in items]
    instructions = (
        "Ты редактор личного русскоязычного дайджеста. На входе ТОЛЬКО публичные RSS-данные. "
        "Верни JSON в формате {\"items\":[{\"id\":\"...\",\"summary\":\"...\",\"impact\":\"...\"}]}. "
        "Для КАЖДОГО id: summary — 1–3 ясных предложения о том, что СООБЩАЕТ издание; "
        "impact — 1 практическое предложение (если оно логически следует из новости). "
        "Никогда не выдумывай факты, даты, числа, цитаты и решения. Если одного заголовка мало — "
        "напиши 'Из заголовка нельзя установить подробности, проверьте источник'. "
        "Для заявлений РФ/Украины/Запада обязательно атрибутируй их стороне и не выдавай за доказанные. "
        "Не приписывай законопроекту статус закона. Не повторяй заголовок дословно."
    )
    try:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                  "temperature": 0.1, "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": instructions},
                               {"role": "user", "content": json.dumps(data, ensure_ascii=False)}]},
            timeout=100,
        )
        resp.raise_for_status()
        result = json.loads(resp.json()["choices"][0]["message"]["content"])
        ids = {x.key for x in items}
        return {x["id"]: (str(x.get("summary", ""))[:950], str(x.get("impact", ""))[:650])
                for x in result.get("items", []) if x.get("id") in ids}
    except (ValueError, KeyError, IndexError, httpx.HTTPError) as ex:
        log.warning("Optional AI explanations failed; using RSS instead: %s", ex)
        return {}
