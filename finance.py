"""Currency chart from dated official Central Bank of Russia XML, not guessed rates."""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

import httpx
from PIL import Image, ImageDraw, ImageFont

CURRENCIES = ("USD", "EUR", "CNY")
SOURCE_URL = "https://www.cbr.ru/scripts/XML_daily.asp"


def parse_rates(xml: bytes) -> tuple[str, dict[str, float]]:
    root = ET.fromstring(xml)
    when = root.attrib.get("Date", "")
    rates = {}
    for node in root.findall("Valute"):
        code = node.findtext("CharCode")
        if code not in CURRENCIES:
            continue
        try:
            rate = Decimal((node.findtext("Value") or "").replace(",", "."))
            nominal = Decimal(node.findtext("Nominal") or "1")
            rates[code] = float(rate / nominal)
        except (InvalidOperation, ZeroDivisionError):
            continue
    return when, rates


async def fetch_cbr_history(client: httpx.AsyncClient, today: date) -> list[tuple[date, dict[str, float]]]:
    """Use last 8 calendar days, dedupe holidays / same official date."""
    dates = [today - timedelta(days=x) for x in range(7, -1, -1)]
    results = []
    for d in dates:
        try:
            response = await client.get(SOURCE_URL, params={"date_req": d.strftime("%d/%m/%Y")}, timeout=12)
            response.raise_for_status()
            published_at, rate = parse_rates(response.content)
            if not all(code in rate for code in CURRENCIES):
                continue
            parsed_day = datetime.strptime(published_at, "%d.%m.%Y").date()
            results.append((parsed_day, rate))
        except (ValueError, httpx.HTTPError, ET.ParseError):
            continue
    # CBR may return same established rate for multiple non-business days.
    unique = {d: rates for d, rates in results}
    return sorted(unique.items())


def chart_png(data: list[tuple[date, dict[str, float]]]) -> bytes:
    """3 honest per-currency sparklines, each with its own axis and actual values."""
    if not data:
        raise ValueError("No CBR data")
    width, height = 1120, 690
    img = Image.new("RGB", (width, height), "#11172b")
    draw = ImageDraw.Draw(img)
    try:
        # Using locally installed fonts by name; no font files included in the ZIP.
        font_title = ImageFont.truetype("DejaVuSans.ttf", 35)
        font = ImageFont.truetype("DejaVuSans.ttf", 25)
        small = ImageFont.truetype("DejaVuSans.ttf", 20)
    except OSError:
        font_title = font = small = ImageFont.load_default()
    draw.text((45, 28), "CBR · Официальные курсы валют", fill="#f6f7fb", font=font_title)
    draw.text((45, 82), "Значения в рублях за 1 единицу валюты · Источник: cbr.ru", fill="#99a6c4", font=small)
    colors = {"USD": "#b59aff", "EUR": "#62d0bb", "CNY": "#efb260"}
    for i, code in enumerate(CURRENCIES):
        y_top = 144 + i * 171
        vals = [row[1][code] for row in data]
        bottom, top = min(vals), max(vals)
        if bottom == top:
            top += 0.1
            bottom -= 0.1
        else:
            margin = (top - bottom) * .25
            bottom -= margin
            top += margin
        draw.rounded_rectangle((42, y_top, 1070, y_top + 148), radius=18, fill="#202943")
        draw.text((62, y_top + 12), code, fill="#f6f7fb", font=font)
        draw.text((190, y_top + 12), f"{vals[-1]:.4f} ₽", fill=colors[code], font=font)
        start_x, end_x = 65, 1042
        coords = []
        for idx, value in enumerate(vals):
            x = start_x + (end_x - start_x) * idx / max(len(vals)-1, 1)
            y = y_top + 113 - ((value - bottom) / (top - bottom)) * 63
            coords.append((round(x), round(y)))
        if len(coords) > 1:
            draw.line(coords, fill=colors[code], width=5, joint="curve")
        for x, y in coords:
            draw.ellipse((x-4,y-4,x+4,y+4), fill=colors[code])
        draw.text((65, y_top + 116), data[0][0].strftime("%d.%m"), fill="#99a6c4", font=small)
        draw.text((940, y_top + 116), data[-1][0].strftime("%d.%m"), fill="#99a6c4", font=small)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
