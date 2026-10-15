"""V2 Rich Messages and safe Telegram HTML fallback, independent of legacy renderer."""
from __future__ import annotations
from collections import defaultdict
from html import escape
from urllib.parse import urlsplit
from news import TOPIC_ORDER
from .builder import DigestSnapshot, DigestItem

def _e(s: str) -> str:
    return escape(str(s),quote=True)

def _evidence_label(status: str) -> str:
    return {
      'official_statement':'Официальное сообщение источника (не независимое подтверждение)',
      'multi_independent':'Сообщения нескольких независимых первоисточников',
      'single_attributed':'По сообщению источника',
      'disputed':'Спорное утверждение · По сообщению источника; позиции расходятся',
      'insufficient':'Недостаточно подтверждений',
    }.get(status,'По сообщению источника')


def _source_links(item: DigestItem) -> str:
    links=[]
    for i,url in enumerate(item.source_urls,1):
        domain=urlsplit(url).hostname or 'источник'
        links.append(f'<a href="{_e(url)}">{_e(domain)} [{i}]</a>')
    return ' · '.join(links)


def render_v2_digest(snapshot: DigestSnapshot) -> tuple[str,list[str]]:
    """Returns rich HTML and <=3200-character HTML fallback messages."""
    groups=defaultdict(list)
    for item in snapshot.items:
        groups[item.category].append(item)
    heading=_e(snapshot.day.strftime('%d.%m.%Y'))
    rich=[f'<h1>DRAGON NEWS</h1>',f'<p><b>{heading}</b> · {len(snapshot.items)} публикаций</p>',
          '<blockquote>Сведения и статусы подтверждения приведены со ссылками на источники.</blockquote>','<hr/>']
    fallback=[f'<b>DRAGON NEWS · {heading}</b>\nСвежих публикаций: {len(snapshot.items)}\n']
    ordered=list(TOPIC_ORDER)+sorted(k for k in groups if k not in TOPIC_ORDER)
    for topic in ordered:
        entries=groups.get(topic,())
        if not entries:
            continue
        rich.append(f'<details open><summary><b>{_e(topic)}</b> · {len(entries)}</summary>')
        for idx,item in enumerate(entries,1):
            label=_evidence_label(item.evidence_status)
            links=_source_links(item)
            rich.append(f'<h3>{idx}. {_e(item.headline)}</h3>')
            rich.append(f'<p><i>{_e(label)}</i></p>')
            if item.facts:
                rich.append(f'<p>{_e(item.facts)}</p>')
            rich.append(f'<p>Источники: {links}</p>')
            # Bound fallback chunks with intact source links; reduce only lengthy body text.
            part=(f'\n<b>{_e(item.headline)}</b>\n<i>{_e(label)}</i>\n'
                  f'{_e(item.facts[:850])}\nИсточники: {links}\n')
            if len(part)>2700:
                part=(f'\n<b>{_e(item.headline[:190])}</b>\n<i>{_e(label)}</i>\n'
                      f'{_e(item.facts[:300])}\nИсточники: {links}\n')
            if len(part)>3200:
                raise ValueError('Too many or excessively long source links')
            if len(fallback[-1])+len(part)>3200:
                fallback.append(f'<b>{_e(topic)}</b> (продолжение)\n')
            fallback[-1]+=part
        rich.append('</details>')
        rich.append('<hr/>')
    return '\n'.join(rich), fallback
