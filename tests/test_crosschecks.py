"""Cross-checks: gaps are reported; none may be severe without the test failing.

Severe (S3 band rule): a gap that could reverse a ranking, or change the sign
of a growth rate that is more than a quarter of a point from zero.
"""

import pytest

from nni_model.crosschecks import (SIX, euro_hours_gap, euro_per_hour_growth, load_inputs,
                                   output_growth, output_level_gap, ranking, report)

NEAR_ZERO = 0.25   # log points: a sign difference this close to zero is not severe


@pytest.fixture(scope="module")
def s():
    return load_inputs()


@pytest.mark.parametrize("economy", SIX)
def test_output_growth_wdi_and_pwt_agree(s, economy):
    c = output_growth(s, economy)
    assert c.mean_abs_gap < 0.3          # measured 0.01-0.23
    assert c.max_abs_gap < 1.0           # largest: Japan 2021, 0.98
    assert c.sign_differs in ([], [2011])  # Japan 2011: -0.20 against +0.02, near zero


def test_japan_2011_sign_difference_is_near_zero(s):
    from nni_model.crosschecks import log_change
    w = log_change(s.get("JPN", "NY.GDP.MKTP.KN", 2010), s.get("JPN", "NY.GDP.MKTP.KN", 2011))
    p = log_change(s.get("JPN", "PWT.RGDPNA", 2010), s.get("JPN", "PWT.RGDPNA", 2011))
    assert abs(w) < NEAR_ZERO and abs(p) < NEAR_ZERO


@pytest.mark.parametrize("economy", SIX)
def test_output_level_gap_is_under_8_percent(s, economy):
    assert abs(output_level_gap(s, economy)) < 8      # measured -4.8% (India) to +7.5% (Japan)


def test_euro_hours_gap_matches_a2_and_stays_under_2_percent(s):
    gaps = {y: (h, p) for y, h, p in euro_hours_gap(s)}
    assert round(gaps[2023][0], 1) == -1.8               # A2, Lavan's run of 26 Oct
    assert all(-2 < h < 0 for h, _ in gaps.values())


def test_euro_area_rank_does_not_change_with_hours_source(s):
    order_pwt, values = ranking(s)
    order_es, _ = ranking(s, euro_hours="Eurostat")
    assert order_pwt == order_es == ["USA", "EA21", "GBR", "JPN", "CHN", "IND"]
    assert values["EA21"] / values["GBR"] - 1 > 0.018    # margin over the UK beats the 1.8% hours gap


def test_euro_2023_per_hour_growth_has_same_sign_with_both_sources(s):
    _, pwt, eurostat = euro_per_hour_growth(s)
    assert pwt < 0 and eurostat < 0
    assert pwt - eurostat == pytest.approx(0.85, abs=0.01)   # A2 said about 0.9 points


def test_report_has_four_checks():
    lines = report()
    assert [l[:2] for l in lines if l[0].isdigit()] == ["1.", "2.", "3.", "4."]
