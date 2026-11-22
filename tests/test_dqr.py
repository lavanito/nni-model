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


def test_nowcast_value_is_capped_at_medium():
    assert rate("P1", "USA").band == HIGH
    r = rate("P1", "USA", flags=["nowcast"])
    assert r.band == MEDIUM and r.reason.startswith("nowcast")


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
    assert us[2023].band == MEDIUM and "also nowcast" in us[2023].reason
    india_2022 = rate_decomposition(NNIDecomposition(snapshot, "IND").year(2022))
    assert india_2022.band == LOW


def test_every_reason_names_criterion_dimension_and_concept():
    import re
    from nni_model.dqr import CRITERIA, MET
    pattern = re.compile(r"^(C-[a-z]+) \(([A-Za-z]+): ([A-Za-z -]+)\): .+")
    for purposes in RATINGS.values():
        for table in purposes.values():
            for band, reason in table.values():
                if band == HIGH:
                    assert reason.startswith(MET)
                    continue
                m = pattern.match(reason)
                assert m, reason
                criterion, dimension, concept = m.groups()
                assert CRITERIA[criterion][0] == dimension and concept in CRITERIA[criterion][1]


def test_s3_example_hours_name_lineage_provenance():
    r = rate("P3", "CHN", inputs=["hours"])
    assert r.band == LOW and r.reason.startswith("CHN hours: C-measured (Lineage: Provenance)")


def test_outlier_flag_names_validity_concept():
    r = rate("P1", "USA", flags=["outlier-suspect"])
    assert r.band == LOW and "(Validity: Values in Specified Range)" in r.reason


def test_why_refuses_a_concept_from_another_dimension():
    from nni_model.dqr import why
    with pytest.raises(ValueError):
        why("C-measured", "Existence", "x")
