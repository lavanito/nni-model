"""Layer B contracts: pass on the real files, block on broken ones."""

from dataclasses import replace

from nni_model.contracts import (CONTRACT_LIST, CONTRACTS, NOT_CONTRACTED, blocked, check,
                                  raw_rows, units_problems)


def test_real_files_pass_every_contract():
    results = check()
    assert len(results) == 3 * len(CONTRACTS)
    assert blocked(results) == []


def test_missing_row_blocks_the_series():
    rows = [r for r in raw_rows() if not (r[0] == "JPN" and r[1] == "SP.POP.TOTL" and r[2] == "2010")]
    results = check(rows)
    assert blocked(results) == ["SP.POP.TOTL"]
    failed = [r for r in results if not r.passed]
    assert failed[0].test == "C-complete" and failed[0].failures == [("JPN", 2010)]


def test_out_of_range_value_blocks_the_series():
    rows = [(e, s, y, "250") if (e, s, y) == ("USA", "PWT.AVH", "2020") else (e, s, y, v)
            for e, s, y, v in raw_rows()]
    assert blocked(check(rows)) == ["PWT.AVH"]


def test_duplicate_row_blocks_the_series():
    rows = raw_rows()
    duplicate = next(r for r in rows if r[1] == "NY.GDP.MKTP.KN")
    assert blocked(check(rows + [duplicate])) == ["NY.GDP.MKTP.KN"]


def test_unknown_economy_code_blocks_the_series():
    rows = raw_rows() + [("XXX", "NY.GNP.MKTP.CN", "2020", "1.0")]
    assert blocked(check(rows)) == ["NY.GNP.MKTP.CN"]


def test_exceptions_are_written_with_reasons():
    for c in CONTRACTS.values():
        for economy, (years, reason) in c.exceptions.items():
            assert reason


def test_unknown_series_blocks_referential_integrity():
    rows = raw_rows() + [("USA", "XX.NEW.SERIES", "2020", "1.0")]
    assert blocked(check(rows)) == ["XX.NEW.SERIES"]


def test_second_metadata_record_breaks_cardinality():
    contracts = CONTRACT_LIST + [CONTRACTS["SP.POP.TOTL"]]
    failed = [r for r in check(contracts=contracts) if not r.passed]
    assert [(r.series, r.test) for r in failed] == [("SP.POP.TOTL", "C-integrity")]


def test_unknown_source_breaks_cardinality():
    contracts = [replace(c, source="Some other database") if c.series == "PWT.AVH" else c
                 for c in CONTRACT_LIST]
    assert blocked(check(contracts=contracts)) == ["PWT.AVH"]


def test_every_series_states_its_units():
    assert units_problems() == []
    ppp = CONTRACTS["PA.NUS.PRVT.PP"]
    assert units_problems([replace(ppp, ppp_base_year=None)]) == [
        ("PA.NUS.PRVT.PP", "international dollars without a PPP base year")]
    population = CONTRACTS["SP.POP.TOTL"]
    assert units_problems([replace(population, price_basis="current")]) == [
        ("SP.POP.TOTL", "price basis or PPP base year without a currency")]


def test_series_without_contract_have_a_reason():
    assert not set(NOT_CONTRACTED) & set(CONTRACTS)
    assert all(NOT_CONTRACTED.values())
