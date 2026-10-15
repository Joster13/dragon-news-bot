"""Event matching tests: do not conflate different claims or legislative stages."""
import unittest
from datetime import datetime, timezone
from dragon_news_v2.models import Article
from dragon_news_v2.matcher import match_articles, group_articles

T=datetime(2026,10,15,9,tzinfo=timezone.utc)

def item(key,title,desc='',source='tass',url=None):
    return Article(key,source,url or 'https://example.org/'+key,title,desc,T,T,None,key)

class EventMatcherTests(unittest.TestCase):
    def test_same_bill_same_stage_merges(self):
        a=item('a','Госдума приняла законопроект № 123456-8 о системе-112 в первом чтении')
        b=item('b','Депутаты одобрили проект закона 123456-8 о системе 112 в I чтении',source='ria')
        self.assertEqual(match_articles(a,b).decision,'same')
        groups=group_articles([b,a])
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0].stage,'reading1')
        self.assertEqual(set(groups[0].article_ids),{'a','b'})
        self.assertIn('123456-8',groups[0].event_key)

    def test_same_bill_next_reading_stays_distinct(self):
        a=item('a','Госдума одобрила законопроект 123456-8 о системе-112 в первом чтении')
        b=item('b','Госдума одобрила законопроект 123456-8 о системе-112 во втором чтении')
        self.assertEqual(match_articles(a,b).decision,'different')
        self.assertEqual(len(group_articles([a,b])),2)

    def test_rejection_vs_approval_stays_distinct(self):
        a=item('a','Парламент принял законопроект 123456-8 о переводах')
        b=item('b','Парламент отклонил законопроект 123456-8 о переводах')
        self.assertEqual(match_articles(a,b).decision,'different')

    def test_duplicate_different_sources(self):
        a=item('a','Роскомнадзор ограничил доступ к VPN-сервису Alpha для пользователей')
        b=item('b','РКН ограничил доступ к VPN-сервису Alpha для пользователей',source='interfax')
        self.assertEqual(match_articles(a,b).decision,'same')

    def test_ambiguous_kept_separate(self):
        a=item('a','Банки ужесточили контроль переводов по новым правилам')
        b=item('b','Банки изменили тарифы для переводов по новым правилам')
        self.assertNotEqual(match_articles(a,b).decision,'same')
        self.assertEqual(len(group_articles([a,b])),2)

    def test_distinct_cve_products_kept_separate(self):
        a=item('a','Уязвимость CVE-2026-12345 в Linux Kernel исправлена','исправление Linux Kernel')
        b=item('b','Уязвимость CVE-2026-12345 в Windows Server исправлена','исправление Windows Server')
        self.assertNotEqual(match_articles(a,b).decision,'same')

    def test_group_is_independent_of_input_order(self):
        a=item('a','Парламент принял поправки 123456-8 в первом чтении')
        b=item('b','Госдума одобрила 123456-8 в I чтении',source='ria')
        c=item('c','Банк России установил новую ставку')
        g1=group_articles([a,b,c])
        g2=group_articles([c,b,a])
        self.assertEqual([(g.event_key,g.article_ids) for g in g1],
                         [(g.event_key,g.article_ids) for g in g2])

    def test_no_merge_between_different_bill_numbers(self):
        a=item('a','Госдума приняла законопроект 123456-8 в первом чтении')
        b=item('b','Госдума приняла законопроект 654321-8 в первом чтении')
        self.assertEqual(match_articles(a,b).decision,'different')

if __name__=='__main__': unittest.main()
