"""Explainable editorial selection without padding or fixed topic quotas."""
import unittest
from datetime import datetime, timedelta, timezone
from dragon_news_v2.matcher import EventGroup
from dragon_news_v2.evidence import EvidenceAssessment
from dragon_news_v2.editor import evaluate_event, rank_events, EditorialDecision

NOW=datetime(2026,10,15,9,tzinfo=timezone.utc)
YESTERDAY=NOW-timedelta(hours=8)

def group(k,title,excerpt='Подробности решения и опубликованные конкретные условия изменения.',published_at=YESTERDAY):
    return EventGroup(k,'',('a'+k,),title,'',published_at,excerpt)

GOOD=EvidenceAssessment('single_attributed',('pressrelease:1',),('one_information_origin',))

class EditorialEngineTests(unittest.TestCase):
    def test_youtube_music_not_vpn(self):
        g=group('noise','YouTube Music начал внедрять ИИ-метки для музыкального контента')
        d=evaluate_event(g,GOOD,NOW)
        self.assertFalse(d.include)
        self.assertIn('rejected_not_substantive',d.reason_codes)

    def test_noncyber_crime_not_infosec(self):
        g=group('noise','Вымогатели на автомойке предстали перед судом')
        self.assertFalse(evaluate_event(g,GOOD,NOW).include)

    def test_cve_is_important(self):
        g=group('cve','Обнаружена критическая уязвимость CVE-2026-12345 в серверном ПО')
        d=evaluate_event(g,GOOD,NOW)
        self.assertTrue(d.include)
        self.assertEqual(d.category,'Инфраструктура и безопасность')

    def test_legal_stage_retained(self):
        g=group('law','Госдума приняла законопроект о маркировке звонков в первом чтении')
        d=evaluate_event(g,GOOD,NOW)
        self.assertTrue(d.include)
        self.assertEqual(d.category,'Законы и правила')
        self.assertTrue(d.rules_version)

    def test_dynamic_priority_fills_from_other_categories(self):
        entries=[
            EditorialDecision('v0',True,'Интернет и VPN',12,'single_attributed',(),'v2'),
            EditorialDecision('x0',True,'Мир и экономика',7,'single_attributed',(),'v2'),
        ]
        selected=rank_events(entries, max_items=10)
        self.assertEqual(len(selected),2)
        self.assertEqual({x.category for x in selected},{'Интернет и VPN','Мир и экономика'})

    def test_never_pad_to_20(self):
        decisions=[EditorialDecision('a',True,'Липецк и Липецкая область',11,'single_attributed',(),'v2'),
                   EditorialDecision('b',False,'Интернет и VPN',0,'insufficient',('insufficient_evidence',),'v2')]
        self.assertEqual([d.event_key for d in rank_events(decisions,28)],['a'])

    def test_expired_item_excluded(self):
        g=group('old','Госдума приняла законопроект о маркировке',published_at=NOW-timedelta(days=3))
        d=evaluate_event(g,GOOD,NOW)
        self.assertFalse(d.include)
        self.assertIn('outside_digest_window',d.reason_codes)

    def test_missing_published_at_excluded(self):
        g=group('undated','Госдума приняла законопроект о маркировке',published_at=None)
        self.assertFalse(evaluate_event(g,GOOD,NOW).include)

    def test_insufficient_verification_excluded(self):
        g=group('untrusted','Госдума приняла законопроект о маркировке')
        status=EvidenceAssessment('insufficient',(),('unrecognized_source',))
        d=evaluate_event(g,status,NOW)
        self.assertFalse(d.include)
        self.assertIn('insufficient_evidence',d.reason_codes)

    def test_limit_and_diversity(self):
        decisions=[EditorialDecision(str(i),True,'Законы и правила' if i<9 else 'Интернет и VPN',
                                     10 if i<9 else 9,'single_attributed',(),'v2') for i in range(12)]
        out=rank_events(decisions,5)
        self.assertEqual(len(out),5)
        self.assertTrue(any(d.category=='Интернет и VPN' for d in out))
        self.assertEqual(len({d.event_key for d in out}),5)

    def test_disputed_claim_not_reported_as_confirmed(self):
        g=group('disputed','Одна из сторон заявила о взятии населённого пункта')
        d=evaluate_event(g,EvidenceAssessment('disputed',('source-a','source-b'),('contradictory_source_claims',)),NOW)
        self.assertFalse(d.include)
        self.assertIn('disputed_claim_requires_review',d.reason_codes)

if __name__=='__main__': unittest.main()
