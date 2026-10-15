"""Source corroboration tests: a press release is not multiple confirmations."""
import unittest
from datetime import datetime,timezone
from dragon_news_v2.models import Article
from dragon_news_v2.matcher import EventGroup
from dragon_news_v2.evidence import assess_evidence

T=datetime(2026,10,15,9,tzinfo=timezone.utc)

def article(id,source='tass',url=None,title='Регулятор объявил о новых правилах'):
    return Article(id,source,url or 'https://example.org/'+id,title,
                   'Описание решения и действующих требований',T,T,None,id)

def grouped(*items):
    return EventGroup('event:policy','',tuple(a.article_id for a in items),items[0].title,'Законы и правила',T)

class EvidenceTests(unittest.TestCase):
    def test_one_press_release_many_outlets_is_one_origin(self):
        a=article('a','tass');b=article('b','interfax');c=article('c','rbc')
        result=assess_evidence(grouped(a,b,c),{a.article_id:a,b.article_id:b,c.article_id:c},
                               {'a':'pressrelease:regulator-42','b':'pressrelease:regulator-42','c':'pressrelease:regulator-42'})
        self.assertEqual(result.status,'single_attributed')
        self.assertEqual(len(result.roots),1)

    def test_primary_statement_does_not_prove_claim(self):
        a=article('a','cbr','https://www.cbr.ru/press/event/?id=100')
        result=assess_evidence(grouped(a),{'a':a},{'a':'official:cbr/100'})
        self.assertEqual(result.status,'official_statement')
        self.assertIn('official_primary_source',result.reason_codes)

    def test_two_independent_reports_multi(self):
        a=article('a','tass');b=article('b','interfax')
        result=assess_evidence(grouped(a,b),{'a':a,'b':b},
                               {'a':'outlet:tass:own-report','b':'outlet:interfax:own-report'})
        self.assertEqual(result.status,'multi_independent')
        self.assertEqual(len(result.roots),2)

    def test_unknown_origins_do_not_create_false_multi(self):
        a=article('a','tass');b=article('b','interfax')
        result=assess_evidence(grouped(a,b),{'a':a,'b':b},{})
        self.assertEqual(result.status,'single_attributed')
        self.assertIn('origin_unverified',result.reason_codes)

    def test_conflicting_war_claim_disputed(self):
        a=article('a','tass',title='Ведомство подтвердило контроль над городом')
        b=article('b','interfax',title='Другая сторона опровергла контроль над городом')
        result=assess_evidence(grouped(a,b),{'a':a,'b':b},
                               {'a':'outlet:tass:1','b':'outlet:interfax:2'})
        self.assertEqual(result.status,'disputed')

    def test_untraceable_claim_insufficient(self):
        a=article('a','unlisted','http://example.org/post')
        result=assess_evidence(grouped(a),{'a':a},{})
        self.assertEqual(result.status,'insufficient')

    def test_incomplete_group_insufficient(self):
        a=article('a','tass')
        result=assess_evidence(EventGroup('e','',('a','missing'),a.title,'',T),
                               {'a':a},{'a':'outlet:tass:own'})
        self.assertEqual(result.status,'insufficient')

if __name__=='__main__': unittest.main()
