import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from finance import parse_rates, chart_png

XML = b'''<ValCurs Date="15.10.2026" name="Foreign Currency Market">
<Valute ID="x"><CharCode>USD</CharCode><Nominal>1</Nominal><Value>85,1234</Value></Valute>
<Valute ID="y"><CharCode>EUR</CharCode><Nominal>1</Nominal><Value>94,5555</Value></Valute>
<Valute ID="z"><CharCode>CNY</CharCode><Nominal>10</Nominal><Value>120,0000</Value></Valute>
</ValCurs>'''

class FinanceTests(unittest.TestCase):
    def test_parse_and_chart(self):
        d, rates = parse_rates(XML)
        self.assertEqual(d, '15.10.2026')
        self.assertAlmostEqual(rates['CNY'], 12.0)
        img = chart_png([(date(2026,10,14), rates), (date(2026,10,15), rates)])
        self.assertTrue(img.startswith(b'\x89PNG'))

if __name__ == '__main__': unittest.main()
