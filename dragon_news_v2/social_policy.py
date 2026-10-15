"""Conservative no-cost suppression of obvious paid promotions and content-free social posts.

Editorial significance and factual verification remain separate downstream checks.
"""
from __future__ import annotations
import re

PAID_PROMOTION = re.compile(
    r'(?:\berid\s*[:=]|\b#реклама\b|\bреклама\s*[.:]\s*'
    r'|\bрекламн[а-я]*\s+интеграц[а-я]*\b'
    r'|\bпартн[её]рск[а-я]*\s+материал\b'
    r'|\bпо\s+промокоду\b|\bпромокод\s*[:\-])',
    re.I,
)
SUBSTANTIVE_SHORT_ALERT = re.compile(
    r'отключ|перекры|эваку|бпла|дрон|пожар|сирен|угроз|'
    r'принял|одобрил|утвердил|вступил|сбой|доступ|запрет|'
    r'свет|водоснабж|уязвимост|CVE-\d|заблокир|задержан|'
    r'штраф|рубл|курс|ставк|вышел|вышла|обнов|патч|анонсир|выпуст',
    re.I,
)


def reject_public_post(text: str) -> bool:
    """Fail on obvious ads and bare captions, not on short emergency notices.

    Only apply to newly approved, metadata-tagged Telegram sources.
    A passed item is *not* verified or guaranteed newsworthy.
    """
    text=text.strip()
    if not text:
        return True
    if PAID_PROMOTION.search(text):
        return True
    if len(text) < 42 and not SUBSTANTIVE_SHORT_ALERT.search(text):
        return True
    return False
