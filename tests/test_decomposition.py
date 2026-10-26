"""Tests for the decomposition on the WDI snapshot of 8 October 2026.

Tests check properties and published figures, never wording.
"""

import pytest

from nni_model.data import EURO_MEMBERS, latest_snapshot, total
from nni_model.decomposition import NNIDecomposition

ECONOMIES = ["USA", "GBR", "JPN", "CHN", "IND", "EA21"]


@pytest.fixture(scope="module")
def snapshot():
    return latest_snapshot()


@pytest.mark.parametrize("economy", ECONOMIES)
def test_parts_add_up_exactly(snapshot, economy):
    results = NNIDecomposition(snapshot, economy).run()
    assert len(results) >= 20
    for r in results:
        assert abs(r.total - r.parts_sum) < 1e-9


@pytest.mark.parametrize("economy", ["USA", "GBR", "JPN", "CHN"])
def test_check_term_is_zero_where_conversion_matches(snapshot, economy):
    for r in NNIDecomposition(snapshot, economy).run():
        if r.chk is not None:
            assert abs(r.chk) < 0.05


def test_check_term_flags_india_conversion(snapshot):
    """WDI converts India's figures at a rate up to 3.2% from the official rate."""
    chks = [r.chk for r in NNIDecomposition(snapshot, "IND").run() if r.chk is not None]
    assert sum(abs(c) > 1 for c in chks) == 13


@pytest.mark.parametrize("economy,last_published", [("USA", 2021), ("GBR", 2018), ("IND", 2021)])
def test_years_after_last_published_nni_are_flagged(snapshot, economy, last_published):
    for r in NNIDecomposition(snapshot, economy).run():
        estimated = any(f.startswith("estimated") for f in r.flags)
        assert estimated == (r.year > last_published)


def test_every_economy_reaches_2024(snapshot):
    for economy in ECONOMIES:
        years = [r.year for r in NNIDecomposition(snapshot, economy).run()]
        assert max(years) >= 2024


def test_india_2022_break_is_flagged(snapshot):
    r = NNIDecomposition(snapshot, "IND").year(2022)
    assert any(f.startswith("break") for f in r.flags)
    assert r.c2 > 6        # deflator mix distorted by the rebase


def test_euro_area_nominal_is_sum_of_members(snapshot):
    assert snapshot.get("EA21", "NY.GDP.MKTP.CN", 2024) == pytest.approx(
        total(snapshot, "NY.GDP.MKTP.CN", 2024))
    assert len(EURO_MEMBERS) == 21


def test_euro_area_chain_link_matches_base_year(snapshot):
    """Volume equals nominal value in the 2021 base year."""
    assert snapshot.get("EA21", "NY.GDP.MKTP.KN", 2021) == pytest.approx(
        snapshot.get("EA21", "NY.GDP.MKTP.CN", 2021))


def test_india_rebase_in_latest_edition(snapshot):
    """2022 nominal GDP of 261.18 lakh crore means the 2022-23 base is in."""
    assert snapshot.get("IND", "NY.GDP.MKTP.CN", 2022) / 1e12 == pytest.approx(261.18, abs=0.01)


@pytest.mark.parametrize("economy", ECONOMIES)
def test_hours_split_adds_up_to_c4(snapshot, economy):
    split = [r for r in NNIDecomposition(snapshot, economy).run() if r.c4a is not None]
    assert [r.year for r in split][-1] == 2023
    for r in split:
        assert abs(r.c4a + r.c4b + r.c4c - r.c4) < 1e-9


def test_india_2019_employment_break_moves_value_between_parts(snapshot):
    r = NNIDecomposition(snapshot, "IND").year(2019)
    assert any("ETD to ILO" in f for f in r.flags)
    assert r.c4c > 7 and r.c4a < -5   # employment jump shifts C4a into C4c


def test_euro_area_hours_match_a2(snapshot):
    """A2 (23 Oct): euro area built from PWT, 1,533 hours per person in 2023."""
    assert round(snapshot.get("EA21", "PWT.AVH", 2023)) == 1533
