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
      ('kommersant','https://t.me/s/kommersant','public_telegram'),
      ('rbc','https://t.me/s/rbc_news','public_telegram'),
      ('ria','https://ria.ru/export/rss2/archive/index.xml','rss'),
      ('izvestia','https://iz.ru/xml/rss/all.xml','rss'),
      ('lenta','https://lenta.ru/rss/','rss'),
      ('gazeta','https://www.gazeta.ru/export/rss/first.xml','rss'),
      ('habr','https://habr.com/ru/rss/news/?fl=ru','rss'),
      ('bbc-russian','https://feeds.bbci.co.uk/russian/rss.xml','rss'),
      ('dw-russian','https://rss.dw.com/xml/rss-ru-all','rss'),
      ('gorod48','https://t.me/s/gorod48ru','public_telegram'),
      ('cbpub','https://t.me/s/Cbpub','public_telegram'),
      ('cb_economics','https://t.me/s/cb_economics','public_telegram'),
      ('lipetsktop1','https://t.me/s/lipetsktop1','public_telegram'),
      ('exploitex','https://t.me/s/exploitex','public_telegram'),
      ('vgtimes','https://t.me/s/vgtimes','public_telegram'),
      ('naebnet','https://t.me/s/naebnet','public_telegram'),
      ('denissexy','https://t.me/s/denissexy','public_telegram'),
      ('habr_com_news','https://t.me/s/habr_com_news','public_telegram'),
    )
    hints = {
        'cbpub': ('Россия — главное',),
        'cb_economics': ('Финансы и крипта',),
        'lipetsktop1': ('Липецк и Липецкая область',),
        'exploitex': ('Интернет и VPN', 'IT, облака и AI'),
        'vgtimes': ('Игры на ПК',),
        'naebnet': ('Интернет и VPN', 'Финансы и крипта', 'IT, облака и AI'),
        'denissexy': ('IT, облака и AI',),
        'habr_com_news': ('IT, облака и AI', 'Инфраструктура и безопасность'),
    }
    return tuple(SourceSpec(sid,url,kind,hints.get(sid,())) for sid,url,kind in urls)
