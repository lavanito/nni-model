"""DQR: the S3 worked examples and the rule's steps."""

import pytest

from nni_model.data import latest_snapshot
from nni_model.decomposition import NNIDecomposition
from nni_model.dqr import ECONOMIES, HIGH, INPUTS, LOW, MEDIUM, RATINGS, rate, rate_decomposition, show


def test_every_input_is_rated_for_every_economy():
    for purpose, inputs in INPUTS.items():
        for series in inputs:
            assert set(RATINGS[series][purpose]) == set(ECONOMIES)


def test_s3_example_productivity_india_china_is_low():
    assert rate("P3", ["IND", "CHN"]).band == LOW


def test_s3_example_uk_growth_first_release_is_medium():
    r = rate("P1", "GBR", flags=["provisional"])
    assert r.band == MEDIUM and r.reason.startswith("provisional")


def test_estimated_value_is_capped_at_medium():
    assert rate("P1", "USA").band == HIGH
    r = rate("P1", "USA", flags=["estimated"])
    assert r.band == MEDIUM and r.reason.startswith("estimated")


def test_check_term_above_one_point_caps_at_low():
    r = rate("P1", "USA", chk=1.5)
    assert r.band == LOW and "CHK" in r.reason


def test_comparison_takes_weakest_economy():
    assert rate("P2", ["USA", "GBR"]).band == MEDIUM      # PPP Medium for both
    assert rate("P2", ["USA", "IND"]).band == LOW         # PPP Low for India


def test_digits_follow_band():
    assert show(1.234, HIGH) == "1.2"
    assert show(1.234, LOW) == "about 1"


@pytest.fixture(scope="module")
def snapshot():
    return latest_snapshot()


def test_decomposition_years_get_a_rating(snapshot):
    us = {r.year: rate_decomposition(r) for r in NNIDecomposition(snapshot, "USA").run()}
    assert us[2021].band == MEDIUM                          # GNI/NNI and PPP Medium for P4
    assert us[2023].band == MEDIUM and "also estimated" in us[2023].reason
    india_2022 = rate_decomposition(NNIDecomposition(snapshot, "IND").year(2022))
    assert india_2022.band == LOW
