"""Data contracts: the Layer B ingestion tests from the S3 data quality statement.

What this file does
    Holds one contract per series (source, units, required economy x year
    rows, allowed range) and runs the three S3 tests on the raw files:

        C-complete   every required economy x year row is present
        C-valid      every value has the right type, lies in range, and uses an allowed code
        C-integrity  rows are unique on economy, series and year; every series
                     has a contract; every contract names its source

    Each test must pass 100%. A series that fails is blocked: the model may not use it.

Inputs
    The raw CSV files in data/wdi/ and data/pwt/.

Outputs
    A Report: per series, pass or fail, with the failing rows.

Required periods (C-coverage, Layer A) are fixed here. Agreed exceptions
are written into the contract, with the reason, so they are visible.
"""

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "data"

SIX = ["USA", "GBR", "JPN", "CHN", "IND"]           # EMU is built from members (EA21)
MEMBERS = ["AUT", "BEL", "BGR", "HRV", "CYP", "EST", "FIN", "FRA", "DEU", "GRC", "IRL",
           "ITA", "LVA", "LTU", "LUX", "MLT", "NLD", "PRT", "SVK", "SVN", "ESP"]
ALLOWED_ECONOMIES = set(SIX) | set(MEMBERS) | {"EMU"}
ALLOWED_YEARS = range(2000, 2026)

WDI = "World Bank, World Development Indicators, edition of 8 October 2026 (CC BY 4.0)"
PWT = "Penn World Table 11.0, Feenstra, Inklaar and Timmer (2015), DOI 10.34894/FABVLR (CC BY 4.0)"


@dataclass
class Contract:
    series: str
    source: str
    units: str
    economies: list
    years: range
    low: float = 0.0                 # values must be greater than low ...
    high: float = float("inf")       # ... and at most high
    exceptions: dict = field(default_factory=dict)   # economy -> (years required, reason)

    def required(self):
        """Every (economy, year) row the contract requires."""
        rows = []
        for e in self.economies:
            years, _ = self.exceptions.get(e, (self.years, ""))
            rows += [(e, y) for y in years]
        return rows


def _wdi(series, units, economies=SIX + MEMBERS, years=range(2000, 2025), **kw):
    return Contract(series, WDI, units, economies, years, **kw)


NNI_EXCEPTIONS = {
    "GBR": (range(2000, 2019), "WDI publishes adjusted NNI for the UK to 2018 only"),
    "GRC": (range(2006, 2022), "WDI publishes adjusted NNI for Greece from 2006 only"),
    "MLT": (range(0), "WDI publishes no adjusted NNI for Malta; the euro area ratio uses the other members"),
}

CONTRACTS = {c.series: c for c in [
    _wdi("NY.GDP.MKTP.CN", "GDP, current local currency"),
    _wdi("NY.GDP.MKTP.KN", "GDP, constant local currency"),
    _wdi("NE.CON.PRVT.CN", "Household consumption, current local currency"),
    _wdi("NE.CON.PRVT.KD", "Household consumption, constant 2015 US$"),
    _wdi("NY.GNP.MKTP.CN", "GNI, current local currency"),
    _wdi("NY.GNP.MKTP.CD", "GNI, current US$"),
    _wdi("NY.ADJ.NNTY.CD", "Adjusted NNI, current US$", years=range(2000, 2022),
         exceptions=NNI_EXCEPTIONS),
    _wdi("NY.ADJ.NNTY.PC.CD", "Adjusted NNI per head, current US$", years=range(2000, 2022),
         exceptions=NNI_EXCEPTIONS),
    _wdi("PA.NUS.FCRF", "Official exchange rate, local currency per US$"),
    _wdi("PA.NUS.PRVT.PP", "PPP factor, household consumption, local currency per int. $"),
    _wdi("SP.POP.TOTL", "Population, persons", low=1e5, high=2e9),
    Contract("PWT.EMP", PWT, "Persons engaged, millions", SIX + MEMBERS, range(2000, 2024),
             low=0.05, high=1000),
    Contract("PWT.AVH", PWT, "Average annual hours per person engaged", SIX + MEMBERS,
             range(2000, 2024), low=1000, high=3000),
]}


def read_wdi(path):
    """Raw rows (economy, series, year, value text) from a WDI long CSV."""
    with open(path, encoding="utf-8") as f:
        return [(r["economy"], r["series"], r["year"], r["value"]) for r in csv.DictReader(f)]


def read_pwt(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((r["economy"], "PWT.EMP", r["year"], r["emp_millions"]))
            rows.append((r["economy"], "PWT.AVH", r["year"], r["avh_hours"]))
    return rows


def raw_rows():
    rows = read_wdi(ROOT / "wdi" / "wdi_latest_2026-10-08.csv")
    rows += read_wdi(ROOT / "wdi" / "wdi_latest_2026-10-08_euro_members.csv")
    rows += read_pwt(ROOT / "pwt" / "pwt110_hours.csv")
    return rows


@dataclass
class Result:
    series: str
    test: str
    passed: bool
    failures: list


def check(rows=None, contracts=CONTRACTS):
    """Run C-complete, C-valid and C-integrity on every contracted series.

    Example:
        >>> results = check()
        >>> all(r.passed for r in results)
        True
    """
    rows = raw_rows() if rows is None else rows
    results = []

    # C-integrity: unique rows; every series used has a contract with a source.
    counts = Counter((e, s, y) for e, s, y, _ in rows)
    duplicates = [k for k, n in counts.items() if n > 1]
    for name, c in contracts.items():
        problems = [d for d in duplicates if d[1] == name]
        if not c.source:
            problems.append(("contract", name, "no source"))
        results.append(Result(name, "C-integrity", not problems, problems))

    values = {}
    for e, s, y, v in rows:
        if s in contracts and v != "":
            values[(e, s, y)] = v

    for name, c in contracts.items():
        # C-complete: every required row is present.
        missing = [(e, y) for e, y in c.required() if (e, name, str(y)) not in values]
        results.append(Result(name, "C-complete", not missing, missing))

        # C-valid: type, range, allowed codes.
        invalid = []
        for (e, s, y), v in values.items():
            if s != name:
                continue
            try:
                number = float(v)
                year = int(y)
            except ValueError:
                invalid.append((e, y, v, "not a number"))
                continue
            if e not in ALLOWED_ECONOMIES:
                invalid.append((e, y, v, "economy code not allowed"))
            elif year not in ALLOWED_YEARS:
                invalid.append((e, y, v, "year outside 2000-2025"))
            elif not (c.low < number <= c.high):
                invalid.append((e, y, v, f"outside ({c.low}, {c.high}]"))
        results.append(Result(name, "C-valid", not invalid, invalid))
    return results


def blocked(results):
    """Series that fail any test; the model must not use them."""
    return sorted({r.series for r in results if not r.passed})
