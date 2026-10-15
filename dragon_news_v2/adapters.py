"""Bounded parsing of public RSS, Atom and Telegram HTML with safe URLs."""
from __future__ import annotations
import hashlib
import html
import ipaddress
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup
from .models import Article
from .source_registry import SourceSpec
from .social_policy import reject_public_post

TRACKING = frozenset({'fbclid','gclid','yclid','mc_cid','mc_eid'})
ATOM_NS = '{http://www.w3.org/2005/Atom}'


def validated_source_url(url: str, allowed_hosts: frozenset[str]) -> str | None:
    """Validate outbound hosts before requesting; callers must reject unapproved redirects."""
    if '\\' in url or any(ord(c)<32 for c in url):
        return None
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme != 'https' or not host or parsed.username is not None or
                parsed.password is not None or parsed.port not in (None,443)):
            return None
        if host.rstrip('.').lower() not in allowed_hosts:
            return None
        try:
            ipaddress.ip_address(host.rstrip('.'))
            return None
        except ValueError:
            pass
        if host.lower() in ('localhost',) or '.localhost' in host.lower():
            return None
        return url
    except ValueError:
        return None


def canonical_url(url: str) -> str:
    p=urlsplit(url.strip())
    query=urlencode(sorted((k,v) for k,v in parse_qsl(p.query,keep_blank_values=True)
                       if not k.lower().startswith('utm_') and k.lower() not in TRACKING))
    path=p.path or '/'
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),path,query,''))


def clean_text(value: str, max_chars: int) -> str:
    return re.sub(r'\s+',' ',html.unescape(BeautifulSoup(value,'html.parser').get_text(' ',strip=True))).strip()[:max_chars]


def parse_date(value: str, atom: bool=False) -> datetime | None:
    if not value:
        return None
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00')) if atom else parsedate_to_datetime(value)
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def make_article(source: SourceSpec, url: str, title: str, desc: str,
                 published: datetime | None, fetched: datetime) -> Article:
    canonical=canonical_url(url)
    digest=hashlib.sha256((source.source_id+'\0'+canonical).encode()).hexdigest()
    return Article(digest, source.source_id, canonical, clean_text(title,250),
                   clean_text(desc,650), published, fetched, None,
                   hashlib.sha256((title+'\0'+desc).encode()).hexdigest())


def parse_feed(source: SourceSpec, payload: bytes, fetched_at: datetime) -> list[Article]:
    if fetched_at.tzinfo is None:
        raise ValueError('fetched_at must be timezone-aware')
    if len(payload)>source.max_bytes:
        raise ValueError('Feed exceeds configured byte limit')
    if source.kind == 'official_web':
        raise ValueError('HTML adapter must be explicitly registered per website')
    if source.kind == 'public_telegram':
        result=[]
        soup=BeautifulSoup(payload,'html.parser')
        # Never accept a post attributed to a different channel in an
        # unexpected HTML response, e.g. an embedded forwarded message.
        path=urlsplit(source.url).path.rstrip('/').split('/')
        expected=path[-1].casefold() if len(path)>=2 else ''
        for card in soup.select('.tgme_widget_message[data-post]')[:180]:
            identifier=card.get('data-post','')
            node=card.select_one('.tgme_widget_message_text')
            t=card.select_one('time[datetime]')
            if not re.fullmatch(r'[A-Za-z0-9_]{4,32}/\d{1,18}',identifier) or not node or not t:
                continue
            if identifier.split('/')[0].casefold()!=expected:
                continue
            published=parse_date(t.get('datetime',''),atom=True)
            content=clean_text(node.get_text(' ',strip=True),900)
            if not content:
                continue
            # Preserve existing established channels' behavior. Only newly
            # curated channels have topic hints and use the spam/noise gate.
            if source.topics and reject_public_post(content):
                continue
            result.append(make_article(source,'https://t.me/'+identifier,content[:210],content,published,fetched_at))
        return result
    try:
        root=ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError('Invalid XML feed') from exc
    rss=root.findall('./channel/item')
    atom=root.findall('.//'+ATOM_NS+'entry') if not rss else []
    result=[]
    for entry in (rss or atom)[:180]:
        if atom:
            title=entry.findtext(ATOM_NS+'title') or ''
            desc=entry.findtext(ATOM_NS+'summary') or entry.findtext(ATOM_NS+'content') or ''
            stamp=entry.findtext(ATOM_NS+'published') or entry.findtext(ATOM_NS+'updated') or ''
            link=next((n.get('href','') for n in entry.findall(ATOM_NS+'link')
                       if n.get('rel','alternate')=='alternate'), '')
            published=parse_date(stamp,atom=True)
        else:
            title=entry.findtext('title') or ''
            desc=entry.findtext('description') or entry.findtext('{http://purl.org/rss/1.0/modules/content/}encoded') or ''
            stamp=entry.findtext('pubDate') or ''
            link=(entry.findtext('link') or '').strip()
            published=parse_date(stamp)
        if not title or not link.startswith('https://'):
            continue
        result.append(make_article(source,link,title,desc,published,fetched_at))
    return result
