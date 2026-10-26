"""Layer B contracts: pass on the real files, block on broken ones."""

from nni_model.contracts import CONTRACTS, blocked, check, raw_rows


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
