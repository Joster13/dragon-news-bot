"""Fact-only digest snapshots and safe Rich Messages rendering."""
import unittest
from datetime import date,datetime,timezone,timedelta
from dragon_news_v2.models import Article
from dragon_news_v2.matcher import EventGroup
from dragon_news_v2.editor import EditorialDecision
from dragon_news_v2.builder import build_digest
from dragon_news_v2.legacy_bridge import render_v2_digest
from rendering import rich_html

NOW=datetime(2026,10,15,9,tzinfo=timezone.utc)
DATE=date(2026,10,15)

def make(id,title,excerpt='Центральный банк опубликовал решение и сроки.',url=None):
    return Article(id,'tass',url or ('https://tass.ru/'+id),title,excerpt,
                   NOW-timedelta(hours=2),NOW-timedelta(hours=1),None,'fingerprint'+id)

def fixture(article,category='Законы и правила',status='single_attributed',event_key='event:1'):
    event=EventGroup(event_key,'reading1',(article.article_id,),article.title,category,article.published_at,article.excerpt)
    decision=EditorialDecision(event_key,True,category,11,status,('category:'+category,),'v2')
    return decision,event

class BuilderTests(unittest.TestCase):
    def test_no_unsubstantiated_why_important(self):
        a=make('a','Госдума одобрила законопроект о новых требованиях')
        d,e=fixture(a)
        snap=build_digest(DATE,[d],{e.event_key:e},{a.article_id:a},NOW)
        text,plain=render_v2_digest(snap)
        self.assertEqual(snap.items[0].facts,a.excerpt)
        self.assertNotIn('Почему важно',text)
        self.assertIn('https://tass.ru/a',text)

    def test_unknown_event_time_not_invented(self):
        a=make('a','Госдума одобрила законопроект о новых требованиях')
        d,e=fixture(a)
        snap=build_digest(DATE,[d],{e.event_key:e},{a.article_id:a},NOW)
        self.assertNotIn('вступил в силу',snap.items[0].facts.casefold())
        self.assertNotIn('вступил в силу',render_v2_digest(snap)[0].casefold())

    def test_law_stage_explicit(self):
        a=make('a','Госдума одобрила законопроект о новых требованиях в первом чтении')
        d,e=fixture(a)
        snap=build_digest(DATE,[d],{e.event_key:e},{a.article_id:a},NOW)
        self.assertIn('первом чтении',snap.items[0].headline)

    def test_source_attribution_for_disputed(self):
        a=make('a','Одна сторона заявила о контроле над районом')
        d,e=fixture(a,'СВО — позиции сторон','disputed')
        snap=build_digest(DATE,[d],{e.event_key:e},{a.article_id:a},NOW)
        html,_=render_v2_digest(snap)
        self.assertIn('Спорное утверждение',html)
        self.assertIn('По сообщению',html)

    def test_escape_untrusted_html_and_link(self):
        a=make('a','Госдума <script>alert(1)</script> одобрила законопроект',
               'Факты <img src=x onerror=alert(1)>', 'https://tass.ru/abc?x=1&y=2')
        d,e=fixture(a)
        snap=build_digest(DATE,[d],{e.event_key:e},{a.article_id:a},NOW)
        h,_=render_v2_digest(snap)
        self.assertNotIn('<script>',h)
        self.assertNotIn('<img',h)
        self.assertIn('&lt;script&gt;',h)
        self.assertIn('&amp;y=2',h)

    def test_unsafe_source_url_rejected(self):
        a=make('a','Госдума одобрила законопроект','Законопроект вступил в первое чтение','javascript:alert(1)')
        d,e=fixture(a)
        with self.assertRaises(ValueError):
            build_digest(DATE,[d],{e.event_key:e},{a.article_id:a},NOW)

    def test_long_report_split_preserves_sources(self):
        decisions=[];events={};articles={}
        for i in range(27):
            a=make(str(i),'Госдума одобрила законопроект № '+str(123456+i)+' в первом чтении',
                   'Опубликованы новые сведения об изменении требований. '*10)
            d,e=fixture(a,event_key='e'+str(i))
            decisions.append(d);events[e.event_key]=e;articles[a.article_id]=a
        snap=build_digest(DATE,decisions,events,articles,NOW)
        rich,chunks=render_v2_digest(snap)
        self.assertEqual(len(snap.items),27)
        self.assertGreater(len(chunks),1)
        self.assertTrue(all(len(chunk)<=3500 for chunk in chunks))
        for i in range(27):
            self.assertIn('https://tass.ru/'+str(i),rich)
            self.assertTrue(any('https://tass.ru/'+str(i) in part for part in chunks))

    def test_rendering_legacy_unchanged(self):
        import inspect
        source=inspect.getsource(rich_html)
        self.assertIn('<h1>DRAGON NEWS</h1>',source)
        a=make('a','Госдума одобрила законопроект')
        d,e=fixture(a)
        snap=build_digest(DATE,[d],{e.event_key:e},{a.article_id:a},NOW)
        self.assertEqual(len(snap.items),1)
        self.assertTrue(render_v2_digest(snap)[0].startswith('<h1>'))

    def test_hash_deterministic(self):
        a=make('a','Госдума одобрила законопроект')
        d,e=fixture(a)
        x=build_digest(DATE,[d],{e.event_key:e},{a.article_id:a},NOW)
        y=build_digest(DATE,[d],{e.event_key:e},{a.article_id:a},NOW)
        self.assertEqual(x.content_hash,y.content_hash)

if __name__=='__main__': unittest.main()
