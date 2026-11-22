"""Tests for the dashboard's control chart rules, limits and page, run in a real headless browser.

The rules live in the page's JavaScript, so the tests render the real page from
synthetic batches and call the same functions the charts use (window.BPM).
"""
import unittest

import pandas as pd
from playwright.sync_api import sync_playwright

from helpers import launch_browser, load_app, make_batches, render

NOISE = [0.3, -0.2, 0.1, -0.4, 0.2, 0.0, -0.1, 0.4, -0.3, 0.2]


def p1_values():
    """30 steady batches around 90, with batch 25 planted far above the rest."""
    values = [90 + NOISE[i % 10] for i in range(30)]
    values[24] = 100.0
    return values


def p3_values():
    """40 batches: 20 steady around 90, then 20 that step up to around 91.5."""
    return [90 + NOISE[i % 10] for i in range(20)] + [91.5 + NOISE[i % 10] for i in range(20)]


def imr_limits(values):
    """Hand calculation of I-MR limits, to check the page against."""
    mean = sum(values) / len(values)
    mr = [abs(b - a) for a, b in zip(values, values[1:])]
    mr_bar = sum(mr) / len(mr)
    sigma = mr_bar / 1.128
    return {"mean": mean, "mrBar": mr_bar, "ucl": mean + 3 * sigma, "lcl": mean - 3 * sigma, "mrUcl": 3.267 * mr_bar}


class DashboardTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = load_app()
        cls.df = pd.concat([
            make_batches("P1", p1_values()),
            make_batches("P2", [90.0, 91.0, 89.5, 90.5, 90.2], start_seq=101),  # too few batches to trend
            make_batches("P3", p3_values(), start_seq=201, api_lot="L3"),
        ], ignore_index=True)
        cls.html = render(cls.app, cls.df)
        cls.pw = sync_playwright().start()
        cls.browser = launch_browser(cls.pw)
        cls.page = cls.browser.new_page()
        cls.page.set_content(cls.html)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def js(self, script, arg=None):
        return self.page.evaluate(script, arg)

    # ---------- the page ----------

    def test_page_renders_and_its_scripts_run(self):
        self.assertEqual(self.page.get_by_text("Batch performance monitor").count(), 1)
        self.assertEqual(self.page.locator("#js-note").count(), 0, "the no-scripts note should be removed")

    def test_only_codes_with_enough_batches_are_trended(self):
        codes = self.js("() => Array.from(document.querySelectorAll('#f-code option')).map(o => o.value)")
        self.assertEqual(sorted(codes), ["P1", "P3"])

    # ---------- pattern rules ----------

    def test_shift_rule_needs_8_in_a_row(self):
        eight = self.js("() => window.BPM.patterns([1,1,1,1,1,1,1,1].map(v => ({v})), 0)")
        self.assertEqual([(r["type"], r["from"], r["to"]) for r in eight], [("Shift", 0, 7)])
        seven = self.js("() => window.BPM.patterns([1,1,1,1,1,1,1].map(v => ({v})), 0)")
        self.assertEqual(seven, [])

    def test_trend_rule_needs_6_in_a_row(self):
        six = self.js("() => window.BPM.patterns([1,2,3,4,5,6].map(v => ({v})), 3.5)")
        self.assertEqual([(r["type"], r["from"], r["to"]) for r in six], [("Trend", 0, 5)])
        five = self.js("() => window.BPM.patterns([1,2,3,4,5].map(v => ({v})), 3)")
        self.assertEqual(five, [])

    # ---------- limits ----------

    def test_limits_match_hand_calculation(self):
        s = self.js("() => window.BPM.series('P1', 'DISSOLUTION_AV')")
        expected = imr_limits(p1_values())
        self.assertEqual(s["n"], 30)
        for key, value in expected.items():
            self.assertAlmostEqual(s[key], value, places=9, msg=key)

    def test_point_beyond_limits_is_flagged(self):
        s = self.js("() => window.BPM.series('P1', 'DISSOLUTION_AV')")
        flagged = [p["batch"] for p in s["pts"] if p.get("flag")]
        self.assertEqual(flagged, ["25"])

    # ---------- frozen limits ----------

    def test_frozen_limits_come_from_the_first_20_batches(self):
        s = self.js("() => window.BPM.series('P3', 'DISSOLUTION_AV', 20)")
        self.assertEqual((s["base"], s["frozen"], s["n"]), (20, True, 40))
        for key, value in imr_limits(p3_values()[:20]).items():
            self.assertAlmostEqual(s[key], value, places=9, msg=key)

    def test_frozen_limits_catch_a_step_that_full_history_limits_absorb(self):
        frozen = self.js("() => window.BPM.series('P3', 'DISSOLUTION_AV', 20)")
        full = self.js("() => window.BPM.series('P3', 'DISSOLUTION_AV')")
        frozen_flags = [p["x"] for p in frozen["pts"] if p.get("flag")]
        full_flags = [p["x"] for p in full["pts"] if p.get("flag")]
        self.assertTrue(frozen_flags and min(frozen_flags) > 20, "only batches after the baseline should break frozen limits")
        self.assertGreater(len(frozen_flags), len(full_flags))

    def test_too_few_batches_to_freeze_uses_every_batch(self):
        s = self.js("() => window.BPM.series('P1', 'DISSOLUTION_AV', 40)")
        self.assertEqual((s["base"], s["frozen"]), (30, False))
        self.assertAlmostEqual(s["ucl"], imr_limits(p1_values())["ucl"], places=9)

    # ---------- capability ----------

    def test_capability_matches_hand_calculation(self):
        values = p1_values()
        n, mean = len(values), sum(values) / len(values)
        sd_overall = (sum((v - mean) ** 2 for v in values) / (n - 1)) ** 0.5
        sd_within = sum(abs(b - a) for a, b in zip(values, values[1:])) / (n - 1) / 1.128
        both = self.js("() => window.BPM.capability(window.BPM.series('P1', 'DISSOLUTION_AV'), 85, 105)")
        self.assertAlmostEqual(both["cpk"], min(105 - mean, mean - 85) / (3 * sd_within), places=9)
        self.assertAlmostEqual(both["ppk"], min(105 - mean, mean - 85) / (3 * sd_overall), places=9)
        lower_only = self.js("() => window.BPM.capability(window.BPM.series('P1', 'DISSOLUTION_AV'), 85, null)")
        self.assertAlmostEqual(lower_only["cpk"], (mean - 85) / (3 * sd_within), places=9)
        none = self.js("() => window.BPM.capability(window.BPM.series('P1', 'DISSOLUTION_AV'), null, null)")
        self.assertIsNone(none)

    # ---------- per-batch signals ----------

    def test_batch_signals_point_to_the_planted_batch(self):
        signals = self.js("() => window.BPM.batchSignals(0)")
        self.assertTrue(signals["25"][0].startswith("Dissolution, average: beyond 3σ"))
        self.assertIn("large jump from the previous batch", signals["26"][0])
        self.assertFalse(any(b in signals for b in ["101", "102", "103", "104", "105"]), "P2 has too few batches to trend")

    # ---------- the controls, end to end ----------

    def fresh_page(self):
        page = self.browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_content(self.html)
        self.addCleanup(page.close)
        return page

    def test_no_script_errors_on_any_tab_or_control(self):
        errors = []
        page = self.browser.new_page(viewport={"width": 1440, "height": 900})
        self.addCleanup(page.close)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.set_content(self.html)
        page.click(".tab[data-tab='trend']")
        for code in ["P1", "P3"]:
            page.select_option("#f-code", code)
            for attr in range(6):
                page.select_option("#f-attr", str(attr))
                for mode in ["all", "base"]:
                    page.select_option("#f-mode", mode)
        page.fill("#f-lsl", "85")
        page.fill("#f-usl", "95")
        page.fill("#f-usl", "")  # cleared again, so only the lower limit counts
        page.click(".tab[data-tab='lots']")
        for mat in range(4):
            page.select_option("#f-mat", str(mat))
            page.select_option("#f-show", "sig")
            page.select_option("#f-show", "all")
        page.click(".tab[data-tab='integrity']")
        self.assertEqual(errors, [])

    def test_frozen_mode_marks_where_limits_freeze(self):
        page = self.fresh_page()
        page.click(".tab[data-tab='trend']")
        page.select_option("#f-code", "P3")
        page.select_option("#f-mode", "base")
        self.assertIn("Limits set from the first 20", page.inner_text("#t-sub"))
        self.assertTrue(page.is_visible("#t-leg-base"))
        self.assertEqual(page.locator("#c-i text", has_text="Limits frozen").count(), 1)

    def test_spec_limits_show_capability_and_reject_a_bad_range(self):
        page = self.fresh_page()
        page.click(".tab[data-tab='trend']")
        page.select_option("#f-code", "P1")
        self.assertIn("Enter a lower or upper spec limit", page.inner_text("#t-cap"))
        page.fill("#f-lsl", "85")
        page.fill("#f-usl", "105")
        expected = page.evaluate("() => window.BPM.capability(window.BPM.series('P1', 'DISSOLUTION_AV'), 85, 105)")
        text = page.inner_text("#t-cap")
        self.assertIn("Cpk " + format(expected["cpk"], ".2f"), text)
        self.assertIn("Ppk " + format(expected["ppk"], ".2f"), text)
        self.assertTrue(page.is_visible("#t-leg-spec"))
        page.fill("#f-lsl", "110")
        self.assertIn("has to be below", page.inner_text("#t-cap"))

    def test_genealogy_shows_signals_and_filters_to_them(self):
        page = self.fresh_page()
        page.click(".tab[data-tab='lots']")
        page.select_option("#f-lot", "Source 1, lot L1")
        rows = page.locator("#l-table tbody tr")
        self.assertEqual(rows.count(), 35, "30 batches of P1 and 5 of P2 use lot L1")
        self.assertIn("Not trended", page.inner_text("#l-table"))
        signals = page.evaluate("() => window.BPM.batchSignals(0)")
        expected = [str(seq) for seq in range(1, 31) if str(seq) in signals]  # P1, in production order
        page.select_option("#f-show", "sig")
        shown = [rows.nth(i).locator("td").first.inner_text() for i in range(rows.count())]
        self.assertEqual(shown, expected)
        self.assertIn("25", shown)
        self.assertIn("Batches with signals", page.inner_text("#l-kpis"))
        self.assertIn(f"{len(expected)} of 35", page.inner_text("#l-kpis"))

    # ---------- integrity checks (Python side) ----------

    def test_integrity_checks_catch_a_duplicate_batch(self):
        checks = {name: ok for name, _, _, _, ok in self.app["integrity_checks"](self.df, len(self.df))}
        self.assertTrue(checks["Batch ID uniqueness"])
        duplicated = pd.concat([self.df, self.df.head(1)], ignore_index=True)
        checks = {name: ok for name, _, _, _, ok in self.app["integrity_checks"](duplicated, len(duplicated))}
        self.assertFalse(checks["Batch ID uniqueness"])


if __name__ == "__main__":
    unittest.main()
