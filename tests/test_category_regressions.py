"""Regressions found in the 15 October Dragon News Telegram preview."""
import unittest
from direct_news import category

class ScreenshotCategoryRegressions(unittest.TestCase):
    def test_rejects_routine_lipetsk_crash(self):
        title = ("Авария с участием шести автомобилей произошла вчера вечером "
                 "на улице Неделина 34-летний водитель ВАЗ-2110 врезался в стоящие машины")
        self.assertIsNone(category(title, forced="Липецк и Липецкая область"))

    def test_keeps_lipetsk_air_raid(self):
        self.assertEqual(
            category("Липецкая область в числе 14 регионов, над которыми перехвачены БПЛА",
                     forced="Липецк и Липецкая область"),
            "Липецк и Липецкая область"
        )

    def test_keeps_lipetsk_utility_shutdown(self):
        self.assertEqual(
            category("В Липецке отключат холодную воду на нескольких улицах",
                     forced="Липецк и Липецкая область"),
            "Липецк и Липецкая область"
        )

    def test_rejects_unrelated_financial_amount(self):
        self.assertNotEqual(
            category("В Дагестане выявили незаконную добычу нефрита на 57 млн рублей"),
            "Финансы и крипта"
        )

    def test_rejects_equipment_procurement_as_finance(self):
        self.assertNotEqual(
            category("В больницы Подмосковья поступило эндоскопическое оборудование на сумму свыше 2 млрд рублей"),
            "Финансы и крипта"
        )

    def test_central_bank_sugar_is_not_finance(self):
        self.assertNotEqual(
            category("ЦБ: производство сахара до 6,3 млн тонн сохранит экспортный потенциал"),
            "Финансы и крипта"
        )

    def test_crypto_p2p_is_finance(self):
        self.assertEqual(
            category("В России запретят P2P-сделки с криптовалютой с июля 2027 года"),
            "Финансы и крипта"
        )

    def test_generic_headline_classified_from_description(self):
        self.assertEqual(
            category("В России запретят один вид сделок",
                     "Прямые P2P-сделки с криптовалютой без посредников будут ограничены"),
            "Финансы и крипта"
        )

    def test_rhetorical_duma_statement_excluded(self):
        self.assertIsNone(
            category("В ЕР раскритиковали оппозицию за внесение законопроектов в виде агитки")
        )

    def test_substantive_duma_legislation_retained(self):
        self.assertEqual(
            category("Госдума приняла в I чтении законопроект о расчете НДФЛ при обмене недвижимости"),
            "Законы и правила"
        )

    def test_rejects_ambassador_chitchat(self):
        self.assertIsNone(
            category("Посол России Зейналова рассказала о ситуации на Маврикии на фоне беспорядков")
        )

    def test_keeps_cybersecurity_incident(self):
        self.assertEqual(
            category("Критическая уязвимость CVE-2026-12345 обнаружена в серверном ПО"),
            "Инфраструктура и безопасность"
        )

    def test_rejects_vpn_truck_blocking(self):
        self.assertIsNone(
            category("Троих задержали после преследования и блокировки грузовика")
        )

if __name__ == "__main__":
    unittest.main()
