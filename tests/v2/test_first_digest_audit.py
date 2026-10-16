"""Regressions grounded in the first 2026-10-16 shadow news audit.

No claim in these tests establishes that a reported regulation actually exists.
"""
import unittest
from datetime import datetime, timedelta, timezone
from dragon_news_v2.models import Article
from dragon_news_v2.matcher import match_articles,group_articles,EventGroup
from dragon_news_v2.editor import evaluate_event
from dragon_news_v2.evidence import EvidenceAssessment
from dragon_news_v2.adapters import parse_feed
from dragon_news_v2.source_registry import SourceSpec

NOW=datetime(2026,10,16,6,tzinfo=timezone.utc)
SINGLE=EvidenceAssessment('single_attributed',('unverified',),('origin_unverified',))

def item(ident,source,title,excerpt=''):
    return Article(ident,source,'https://example.org/'+ident,title,excerpt,
                   NOW-timedelta(hours=3),NOW-timedelta(hours=2),None,ident)

def ev(a):
    return EventGroup('event:'+a.article_id,'',(a.article_id,),a.title,'',a.published_at,a.excerpt)


class DuplicateReportsTests(unittest.TestCase):
    def test_technology_levy_reprints_merge_by_distinctive_subject(self):
        a=item('tass-tech','tass','Правительство утвердило технологический сбор на электронику')
        b=item('interfax-tech','interfax','Кабмин установил технологический сбор для производителей электроники')
        self.assertEqual(match_articles(a,b).decision,'same')
        self.assertEqual(len(group_articles([a,b])),1)

    def test_p2p_rewrites_with_same_future_date_are_one_claim(self):
        a=item('a','rbc','ЦБ сообщил о запрете P2P-переводов криптовалют с 1 июля 2027 года')
        b=item('b','cb_economics','Запрет P2P переводов криптовалют с 1 июля 2027 года: новые правила ЦБ')
        self.assertEqual(match_articles(a,b).decision,'same')

    def test_distinct_p2p_future_dates_are_not_merged(self):
        a=item('a','rbc','Запрет P2P переводов криптовалют с 1 июля 2027 года')
        b=item('b','cb_economics','Запрет P2P переводов криптовалют с 1 августа 2027 года')
        self.assertNotEqual(match_articles(a,b).decision,'same')

    def test_legislative_reading_and_effective_law_are_not_merged(self):
        a=item('a','tass','Госдума приняла законопроект о платежах в первом чтении')
        b=item('b','interfax','Закон о платежах вступил в силу')
        self.assertEqual(match_articles(a,b).decision,'different')

    def test_warning_and_all_clear_remain_distinct(self):
        a=item('a','lipetsktop1','В Липецкой области объявлена угроза БПЛА')
        b=item('b','gorod48','В Липецкой области отменена угроза БПЛА, объявлен отбой')
        self.assertNotEqual(match_articles(a,b).decision,'same')


class EditorialTrustTests(unittest.TestCase):
    def test_unsourced_future_legal_ban_not_presented_as_enacted(self):
        a=item('a','cb_economics',
               'С 1 июля 2027 года полностью запретят P2P-переводы криптовалют')
        d=evaluate_event(ev(a),SINGLE,NOW)
        self.assertFalse(d.include)
        self.assertIn('future_legal_claim_unverified',d.reason_codes)

    def test_dated_proposal_remains_a_proposal(self):
        a=item('a','tass','Госдума рассмотрит законопроект о запрете переводов в ноябре')
        d=evaluate_event(ev(a),SINGLE,NOW)
        self.assertNotIn('future_legal_claim_unverified',d.reason_codes)

    def test_fictional_series_about_historical_events_not_world_news(self):
        a=item('a','Cbpub','Премьера сериала об исторических событиях 1954 года в СССР')
        d=evaluate_event(ev(a),SINGLE,NOW)
        self.assertFalse(d.include)
        self.assertIn('entertainment_not_news',d.reason_codes)

    def test_real_emergency_alert_still_allowed(self):
        a=item('a','lipetsktop1','В Липецке отключили электроснабжение двух улиц')
        g=EventGroup('alert','',(a.article_id,),a.title,'Липецк и Липецкая область',
                     a.published_at,a.excerpt)
        self.assertTrue(evaluate_event(g,SINGLE,NOW).include)


class ResolvedAlertTests(unittest.TestCase):
    def test_bpla_warning_and_later_all_clear_not_presented_as_active(self):
        from dragon_news_v2.editor import suppress_resolved_alerts
        warning=item('warn','lipetsktop1','В Липецкой области объявлена угроза БПЛА')
        release=item('clear','gorod48','В Липецкой области объявлен отбой угрозы БПЛА')
        warning_group=EventGroup('warning','',('warn',),warning.title,
                                 'Липецк и Липецкая область',NOW-timedelta(hours=5),warning.excerpt)
        clear_group=EventGroup('clear','',('clear',),release.title,
                               'Липецк и Липецкая область',NOW-timedelta(hours=2),release.excerpt)
        decisions=[evaluate_event(e,SINGLE,NOW) for e in (warning_group,clear_group)]
        result=suppress_resolved_alerts([warning_group,clear_group],decisions)
        self.assertEqual(len(result),2)
        self.assertFalse(result[0].include)
        self.assertFalse(result[1].include)
        self.assertIn('resolved_warning',result[0].reason_codes)

    def test_unverified_or_rejected_clearance_cannot_hide_active_warning(self):
        from dragon_news_v2.editor import suppress_resolved_alerts,EditorialDecision
        warning=EventGroup('w','',('a',),'В Липецкой области объявлена угроза БПЛА',
                           'Липецк и Липецкая область',NOW-timedelta(hours=3),'')
        doubtful=EventGroup('c','',('b',),'В Липецкой области объявлен отбой угрозы БПЛА',
                            'Липецк и Липецкая область',NOW-timedelta(hours=1),'')
        ds=[EditorialDecision('w',True,'Липецк и Липецкая область',10,'single_attributed',(),'v2'),
            EditorialDecision('c',False,'Липецк и Липецкая область',0,'insufficient',
                              ('insufficient_evidence',),'v2')]
        result=suppress_resolved_alerts([warning,doubtful],ds)
        self.assertTrue(result[0].include)
        self.assertFalse(result[1].include)

    def test_later_all_clear_different_region_keeps_lipetsk_warning(self):
        from dragon_news_v2.editor import suppress_resolved_alerts,EditorialDecision
        warning=EventGroup('w','',('a',),'В Липецкой области объявлена угроза БПЛА',
                           'Липецк и Липецкая область',NOW-timedelta(hours=3),'')
        elsewhere=EventGroup('c','',('b',),'В Воронежской области объявлен отбой угрозы БПЛА',
                             'Россия — главное',NOW-timedelta(hours=1),'')
        ds=[EditorialDecision('w',True,'Липецк и Липецкая область',10,'single_attributed',(),'v2'),
            EditorialDecision('c',True,'Россия — главное',10,'single_attributed',(),'v2')]
        self.assertTrue(suppress_resolved_alerts([warning,elsewhere],ds)[0].include)


class TelegramTextCleanupTests(unittest.TestCase):
    def source(self):
        return SourceSpec('cbpub','https://t.me/s/Cbpub','public_telegram',('Россия — главное',))

    def parse(self,body):
        html=('<div class="tgme_widget_message" data-post="Cbpub/890">'
              '<div class="tgme_widget_message_text">'+body+'</div>'
              '<time datetime="2026-10-16T03:30:00+00:00"></time></div>').encode()
        return parse_feed(self.source(),html,NOW)

    def test_footer_calls_to_action_removed(self):
        posts=self.parse('В России утвердили новые правила работы системы.<br>'
                         'Подробности опубликованы на официальном сайте.<br>'
                         'Подписаться<br>Написать нам<br>Читать далее')
        self.assertEqual(len(posts),1)
        self.assertNotIn('Подписаться',posts[0].excerpt)
        self.assertNotIn('Написать нам',posts[0].title)
        self.assertNotIn('Читать далее',posts[0].excerpt)
        self.assertIn('Подробности',posts[0].excerpt)

    def test_long_telegram_title_ends_on_word_boundary(self):
        text=('Правительство обновило требования к эксплуатации серверов в государственных '
              'информационных системах. ' + 'Опубликованы подробности нового документа. '*18)
        posts=self.parse(text)
        self.assertEqual(len(posts),1)
        self.assertLessEqual(len(posts[0].title),210)
        self.assertTrue(posts[0].title.endswith('.') or posts[0].title.endswith('…'))
        self.assertNotIn('Подписаться',posts[0].title)

if __name__=='__main__':
    unittest.main()
