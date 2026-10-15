"""Post-RSS editorial relevance gate.

Topic classification is not an inclusion decision. Restrict the published
digest to consequential changes; unrelated crime, generic advice, and proposals
that have not become infrastructure projects should not fill topic quotas.
"""
from __future__ import annotations
import re

def match(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text, re.I))

CRIME = (
    r"\bэкстрадирова[а-я]*\b|\bэкстрадиц[а-я]*\b|"
    r"\bобвиняем[а-я]*\b|\bвымогател[а-я]*\b|"
    r"\bуголовн[а-я]*\s+дел[а-я]*\b|"
    r"\bпредстал[а-я]*\s+перед\s+судом\b|"
    r"\bарест[а-я]*\b|\bзадерж[а-я]*\b|"
    r"\bпытал[а-я]*\b|\bубийств[а-я]*\b|"
    r"\bизнасилова[а-я]*\b|\bпохитил[а-я]*\b"
)
CYBER_ACTUAL = (
    r"\bCVE-\d{4}-\d+\b|"
    r"\bкибератак[а-я]*\b|\bвзлом[а-я]*\b|"
    r"\bутечк[а-я]*\s+данных\b|\bвредоносн[а-я]*\b|"
    r"\bransomware\b|\bшифровальщик[а-я]*\b|"
    r"\bуязвимост[а-я]*\b|\bDDoS\b"
)
TECH_CHANGE = (
    r"\bпредставил[а-я]*\b|\bанонсирова[а-я]*\b|"
    r"\bзапустил[а-я]*\b|\bвыпустил[а-я]*\b|"
    r"\bобновил[а-я]*\b|\bвнедрил[а-я]*\b|"
    r"\bоткрыл[а-я]*\b|\bдоступн[а-я]*\b|"
    r"\bизменил[а-я]*\b|\bограничил[а-я]*\b|"
    r"\bотключил[а-я]*\b|\bзакрыл[а-я]*\b|"
    r"\bотменил[а-я]*\b|\bподтвердил[а-я]*\b|"
    r"\bуязвимост[а-я]*\b|\bCVE-\d{4}-\d+\b"
)
TELECOM = (
    r"\bVPN\b|\bVLESS\b|\bWireGuard\b|\bТСПУ\b|"
    r"\bDPI\b|\bРКН\b|роскомнадзор|"
    r"\btelegram\b|\bтелеграм[а-я]*\b|"
    r"интернет|мессенджер|провайдер|"
    r"(?:блокиров|огранич|замедл|недоступн)[а-я ]*(?:сайт|доступ|связ|youtube|ютуб)|"
    r"протокол[а-я ]+обход|\bDNS\b"
)
ACCESS_CHANGE = (
    r"\bблокиров[а-я]*\b|\bзаблокирова[а-я]*\b|"
    r"\bограничил[а-я]*\b|\bнедоступн[а-я]*\b|"
    r"\bзамедл[а-я]*\b|\bотключил[а-я]*\b|"
    r"\bвосстановил[а-я]*\b|\bсбой\b|"
    r"\bнарушен[а-я]*\b|\bзапрет[а-я]*\b|"
    r"\bввел[а-я]*\b|\bввёл[а-я]*\b|"
    r"\bизменил[а-я]*\b|\bразрешил[а-я]*\b"
)
ACTUAL_INFRA = (
    r"\bоткрыл[а-я]*\b|\bвв[её]л[а-я]*\s+в\s+эксплуатаци|"
    r"\bзапустил[а-я]*\b|\bпостроил[а-я]*\b|"
    r"\bначал[а-я]*\s+строительств|"
    r"\bвыделил[а-я]*\s+финансирован|"
    r"\bподписал[а-я]*\s+соглашени|"
    r"\bвывел[а-я]*\s+из\s+строя|"
    r"\bостанов[а-я]*\s+работ|\bсбой\b|"
    r"\bнов[а-я]*\s+(?:сервер|процессор|ускорител|платформ)[а-я]*\b"
)
ADVICE = (
    r"(?:^|\s)назван[а-я]*\s+(?:три|пять|главн|основн)|"
    r"\bправил[ао]\s+формировани[яе]\b|"
    r"\bрассказал[а-я]*\s+о\s+праве\b|"
    r"\bкак\s+(?:сэкономить|накопить|выбрать|сформировать)\b|"
    r"\bэксперт[а-я]*\s+(?:назвал|рассказал|объяснил)[а-я]*\b"
)
OPINION = (
    r"\bвыступил[а-я]*\s+против\b|"
    r"\bзаявил[а-я]*\s+о\s+влияни[яе]\b|"
    r"\bвывед[её]т\s+экономик[а-я]*\b|"
    r"\bпризвал[а-я]*\b|"
    r"\bзаинтересовал[а-я]*\b|"
    r"\bпредложил[а-я]*\s+(?:возводить|размещать|перенести|строить)\b"
)

def is_publishable(item) -> bool:
    title = (item.title or "").strip()
    summary = (item.summary or "").strip()
    topic = item.topic
    if not title:
        return False

    if match(CRIME, title) and not match(CYBER_ACTUAL, title):
        if topic not in ("Липецк и Липецкая область", "Россия — главное"):
            return False
    if match(ADVICE, title):
        return False

    if topic == "Липецк и Липецкая область":
        return True

    if topic == "Интернет и VPN":
        if match(r"\byoutube\s+music\b", title) and not match(ACCESS_CHANGE, title):
            return False
        if not match(TELECOM, title):
            return False
        return bool(match(ACCESS_CHANGE, title) or match(
            r"\bVPN\b|\bVLESS\b|\bWireGuard\b|\bТСПУ\b|\bDPI\b|\bРКН\b|роскомнадзор|"
            r"\btelegram\b.*(?:bot|бот|api|запуст|обнов)|"
            r"(?:bot|бот|api).{0,30}\btelegram\b", title))

    if topic == "Финансы и крипта":
        if match(r"\bэкстрадирова[а-я]*\b|\bуголовн[а-я]*\b|\bприговор\b", title):
            return False
        return True

    if topic == "IT, облака и AI":
        if match(CRIME, title) and not match(CYBER_ACTUAL, title):
            return False
        if match(OPINION, title) and not match(
            r"\bпредставил[а-я]*\b|\bзапустил[а-я]*\b|\bодобрил[а-я]*\b", title
        ):
            return False
        if match(r"\bOpenAI\b", title) and match(
            r"\bтуалетн[а-я]*\b|\bинженер[а-я]*\s+арест", title
        ):
            return False
        if match(r"\bКИИ\b|бел[а-я]*\s+списк|\bCVE-\d", title):
            return True
        return bool(match(TECH_CHANGE, title))

    if topic == "Инфраструктура и безопасность":
        if match(CYBER_ACTUAL, title):
            return True
        if match(CRIME, title) or match(OPINION, title):
            return False
        return bool(match(ACTUAL_INFRA, title))

    if topic == "Игры на ПК":
        if match(r"\b(?:19\d{2}|200\d)\s*год", title) and not match(
            r"ремастер|ремейк", title
        ):
            return False
        return True

    if topic == "СВО — позиции сторон":
        if match(
            r"в\s+ульяновск[а-я]*.*\bок[оё]н[а-я]*\b|"
            r"\b25\s+сентября\b.*\bок[оё]н[а-я]*\b", title
        ):
            return False
        if match(r"\b(льгот|госпошлин|налог|пособи)[а-я]*\b", title):
            return False
        return len(summary) >= 35

    if topic == "Мир и экономика":
        if match(CRIME, title):
            return False
        if match(r"\bзаявил\b|\bпризвал\b", title) and not match(
            r"\bдоговор|утверд|соглашен", title
        ):
            return False
        return True

    if topic == "Законы и правила":
        return True

    if topic == "Россия — главное":
        if match(CRIME, title) and not match(r"крупн|массов|нац|федерал", title):
            return False
        return True

    return False
