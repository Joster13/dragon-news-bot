"""Explicit registry of existing public feeds, without credentials."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

SourceKind = Literal['rss','atom','public_telegram','official_web']

@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    url: str
    kind: SourceKind
    topics: tuple[str, ...]
    max_bytes: int = 1_500_000
    min_interval_s: int = 3600


def load_source_specs() -> tuple[SourceSpec,...]:
    """Seed only already used open feeds; health checked by collector, not assumed."""
    urls = (
      ('interfax','https://www.interfax.ru/rss','rss'),
      ('tass','https://tass.ru/rss/v2.xml','rss'),
      ('kommersant','https://www.kommersant.ru/RSS/news.xml','rss'),
      ('rbc','https://rssexport.rbc.ru/rbcnews/news/30/full.rss','rss'),
      ('ria','https://ria.ru/export/rss2/archive/index.xml','rss'),
      ('izvestia','https://iz.ru/xml/rss/all.xml','rss'),
      ('lenta','https://lenta.ru/rss/','rss'),
      ('gazeta','https://www.gazeta.ru/export/rss/lenta.xml','rss'),
      ('habr','https://habr.com/ru/rss/news/?fl=ru','rss'),
      ('bbc-russian','https://feeds.bbci.co.uk/russian/rss.xml','rss'),
      ('dw-russian','https://rss.dw.com/xml/rss-ru-all','rss'),
      ('gorod48','https://t.me/s/gorod48ru','public_telegram'),
    )
    return tuple(SourceSpec(sid,url,kind,()) for sid,url,kind in urls)
