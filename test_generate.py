import json
import tempfile
import unittest
from pathlib import Path
from generate import load_records, compute_summary, render


class JournalTests(unittest.TestCase):
    def load(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'records.json'
            original = json.dumps(rows, ensure_ascii=False).encode()
            path.write_bytes(original)
            result = load_records(path)
            self.assertEqual(path.read_bytes(), original)
            return result

    def test_explicit_tests_excluded_but_real_small_or_free_charges_retained(self):
        rows, excluded = self.load([
            {'date':'2026-09-25','station':'连通性自测-TEST-请删除','kwh':.001,'amount':.01},
            {'date':'2026-09-19','station':'真实小额','kwh':.1,'amount':0},
            {'date':'2026-09-20','station':'有效记录','kwh':20,'amount':10},
            {'date':'2026-09-21','station':'真实名称','kwh':10,'amount':5,'is_test':True},
        ])
        self.assertEqual(len(rows),2)
        self.assertEqual(excluded,{'test':2,'invalid':0})
        self.assertEqual(compute_summary(rows)['latest_date'],'2026-09-20')

    def test_weighted_price_and_actual_payment_do_not_add_coupon(self):
        rows, _ = self.load([
            {'date':'2026-06-01','station':'A','kwh':10,'amount':10,'coupon':5},
            {'date':'2026-06-02','station':'B','kwh':40,'amount':20},
        ])
        summary=compute_summary(rows)
        self.assertEqual(summary['avg_price'],.6)
        self.assertEqual(summary['total_amount'],30)
        self.assertEqual(summary['total_coupon'],5)

    def test_dates_finite_values_and_missing_optional_fields(self):
        rows, excluded = self.load([
            {'date':'2026-02-30','kwh':10,'amount':1},
            {'date':'2026-06-01','kwh':'NaN','amount':1},
            {'date':'2026-06-01','kwh':10,'amount':-1},
            {'date':'2026-06-01','kwh':10,'amount':0,'start_soc':110},
        ])
        self.assertEqual(excluded['invalid'],3)
        self.assertEqual(rows[0]['station'],'未记录站点')
        self.assertIsNone(rows[0]['start_soc'])
        self.assertIsNone(rows[0]['duration_min'])

    def test_aliases_are_conservative_and_original_name_is_retained(self):
        rows, _ = self.load([
            {'date':'2026-06-02','station':'莲城充电-体育中心二期充电站','kwh':10,'amount':1},
            {'date':'2026-06-01','station':'莲城充电·湘潭交发体育中心充电站','kwh':10,'amount':1},
        ])
        self.assertNotEqual(rows[0]['station'],rows[1]['station'])
        self.assertEqual(rows[1]['original_station'],'莲城充电-体育中心二期充电站')

    def test_untrusted_record_cannot_close_json_script(self):
        rows, _ = self.load([{'date':'2026-06-01','station':'</script><script>alert(1)</script>','kwh':10,'amount':1}])
        page=render(rows)
        self.assertNotIn('</script><script>alert(1)</script>',page)
        self.assertIn('\\u003c/script>',page)
        self.assertNotIn('趋势上升=电池可能在衰减',page)
        self.assertNotIn('最佳效率',page)

    def test_empty_dataset_still_generates_standalone_page(self):
        page=render([],excluded={'test':1,'invalid':0})
        self.assertIn('"records":[]',page)
        self.assertNotIn('<!-- INLINE_',page)
        self.assertIsNone(compute_summary([])['avg_price'])


if __name__=='__main__':
    unittest.main()
