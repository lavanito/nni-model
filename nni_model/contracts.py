"""Data contracts: the Layer B ingestion tests from the S3 data quality statement.

What this file does
    Holds one contract per series (source, units, required economy x year
    rows, allowed range) and runs the three S3 tests on the raw files:

        C-complete   every required economy x year row is present
        C-valid      every value has the right type, lies in range, and uses an allowed code
        C-integrity  Uniqueness: rows are unique on economy, series and year.
                     Referential Integrity: every series in the raw files has a
                     contract, or is listed in NOT_CONTRACTED with a reason.
                     Cardinality: each series has one contract (its metadata
                     record) and one source from SOURCES.

    It also runs the S3 units test (C-representation: Includes Measurement
    Units): every money series states its currency and price basis, and every
    series in international dollars states its PPP base year.

    Each test must pass 100%. A series that fails is blocked: the model may not use it.

Inputs
    The raw CSV files in nni_model/data/wdi/ and nni_model/data/pwt/.

Outputs
    A Report: per series, pass or fail, with the failing rows.

Required periods (C-coverage, Layer A) are fixed here. Agreed exceptions
are written into the contract, with the reason, so they are visible.
"""

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "data"

SIX = ["USA", "GBR", "JPN", "CHN", "IND"]           # EMU is built from members (EA21)
MEMBERS = ["AUT", "BEL", "BGR", "HRV", "CYP", "EST", "FIN", "FRA", "DEU", "GRC", "IRL",
           "ITA", "LVA", "LTU", "LUX", "MLT", "NLD", "PRT", "SVK", "SVN", "ESP"]
ALLOWED_ECONOMIES = set(SIX) | set(MEMBERS) | {"EMU"}
ALLOWED_YEARS = range(2000, 2026)

WDI = "World Bank, World Development Indicators, edition of 8 October 2026 (CC BY 4.0)"
PWT = "Penn World Table 11.0, Feenstra, Inklaar and Timmer (2015), DOI 10.34894/FABVLR (CC BY 4.0)"
SOURCES = [WDI, PWT]

# Series in the raw files that the model does not use, so they have no contract.
NOT_CONTRACTED = {
    "NY.GDP.DEFL.ZS": "not used: the model works out the GDP deflator from current and constant GDP",
    "NY.GDP.MKTP.CD": "not used: GDP in US$ is not an input to any purpose",
    "NY.GDP.PCAP.KN": "not used: the model works out GDP per head from GDP and population",
    "NY.GDP.MKTP.PP.KD": "cross-check only (reported, not rated): per-hour output against Eurostat",
    "NY.GNP.PCAP.PP.CD": "cross-check only (reported, not rated): GNI per head at PPP",
    "PA.NUS.PPP": "cross-check only (reported, not rated): PPP for GDP against household consumption",
}


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
    currency: str = None        # money series only, e.g. "local currency", "US$"
    price_basis: str = None     # money series only: "current" or "constant ..."
    ppp_base_year: int = None   # series in international dollars only

    def required(self):
        """Every (economy, year) row the contract requires."""
        rows = []
        for e in self.economies:
            years, _ = self.exceptions.get(e, (self.years, ""))
            rows += [(e, y) for y in years]
        return rows


def _wdi(series, units, economies=SIX + MEMBERS, years=range(2000, 2025), **kw):
    return Contract(series, WDI, units, economies, years, **kw)


LCU, USD, INTL = "local currency", "US$", "international $"


NNI_EXCEPTIONS = {
    "GBR": (range(2000, 2019), "WDI publishes adjusted NNI for the UK to 2018 only"),
    "GRC": (range(2006, 2022), "WDI publishes adjusted NNI for Greece from 2006 only"),
    "MLT": (range(0), "WDI publishes no adjusted NNI for Malta; the euro area ratio uses the other members"),
}

# One contract per series: the series' metadata record. Cardinality is checked
# on this list, so a second record for a series is caught, not overwritten.
CONTRACT_LIST = [
    _wdi("NY.GDP.MKTP.CN", "GDP, current local currency", currency=LCU, price_basis="current"),
    _wdi("NY.GDP.MKTP.KN", "GDP, constant local currency", currency=LCU,
         price_basis="constant (base year set by each national producer)"),
    _wdi("NE.CON.PRVT.CN", "Household consumption, current local currency", currency=LCU,
         price_basis="current"),
    _wdi("NE.CON.PRVT.KD", "Household consumption, constant 2015 US$", currency=USD,
         price_basis="constant 2015"),
    _wdi("NY.GNP.MKTP.CN", "GNI, current local currency", currency=LCU, price_basis="current"),
    _wdi("NY.GNP.MKTP.CD", "GNI, current US$", currency=USD, price_basis="current"),
    _wdi("NY.ADJ.NNTY.CD", "Adjusted NNI, current US$", years=range(2000, 2022),
         exceptions=NNI_EXCEPTIONS, currency=USD, price_basis="current"),
    _wdi("NY.ADJ.NNTY.PC.CD", "Adjusted NNI per head, current US$", years=range(2000, 2022),
         exceptions=NNI_EXCEPTIONS, currency=USD, price_basis="current"),
    _wdi("PA.NUS.FCRF", "Official exchange rate, local currency per US$, period average",
         currency=f"{LCU} per {USD}", price_basis="current"),
    _wdi("PA.NUS.PRVT.PP", "PPP factor, household consumption, local currency per int. $",
         currency=f"{LCU} per {INTL}", price_basis="current", ppp_base_year=2021),
    _wdi("SP.POP.TOTL", "Population, persons", low=1e5, high=2e9),
    Contract("PWT.EMP", PWT, "Persons engaged, millions", SIX + MEMBERS, range(2000, 2024),
             low=0.05, high=1000),
    Contract("PWT.AVH", PWT, "Average annual hours per person engaged", SIX + MEMBERS,
             range(2000, 2024), low=1000, high=3000),
]
CONTRACTS = {c.series: c for c in CONTRACT_LIST}


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


def units_problems(contracts=CONTRACT_LIST):
    """The S3 units test (C-representation: Includes Measurement Units).

    A money series states its currency and price basis; a series in
    international dollars also states its PPP base year; a series that is
    not money (persons, hours) states neither. Returns (series, problem) pairs.

    Example:
        >>> units_problems()
        []
        >>> units_problems([Contract("X", WDI, "GDP, current US$", [], range(0), currency=USD)])
        [('X', 'money series without a price basis')]
    """
    problems = []
    for c in contracts:
        if not c.units:
            problems.append((c.series, "no units text"))
        if c.currency is None:
            if c.price_basis or c.ppp_base_year:
                problems.append((c.series, "price basis or PPP base year without a currency"))
            continue
        if not c.price_basis:
            problems.append((c.series, "money series without a price basis"))
        if INTL in c.currency and c.ppp_base_year is None:
            problems.append((c.series, "international dollars without a PPP base year"))
    return problems


def check(rows=None, contracts=CONTRACT_LIST):
    """Run C-complete, C-valid and C-integrity on every contracted series.

    Example:
        >>> results = check()
        >>> all(r.passed for r in results)
        True
    """
    rows = raw_rows() if rows is None else rows
    records = Counter(c.series for c in contracts)
    contracts = {c.series: c for c in contracts}
    results = []

    # C-integrity. Uniqueness: one row per economy, series and year.
    # Cardinality: one contract (metadata record) and one known source per series.
    counts = Counter((e, s, y) for e, s, y, _ in rows)
    duplicates = [k for k, n in counts.items() if n > 1]
    for name, c in contracts.items():
        problems = [d for d in duplicates if d[1] == name]
        if records[name] > 1:
            problems.append(("contract", name, f"{records[name]} metadata records"))
        if c.source not in SOURCES:
            problems.append(("contract", name, "source is not one of SOURCES"))
        results.append(Result(name, "C-integrity", not problems, problems))

    # Referential Integrity: every series in the raw files has a contract,
    # or a stated reason for having none. An unknown series is blocked.
    for name in sorted({s for _, s, _, _ in rows} - set(contracts) - set(NOT_CONTRACTED)):
        results.append(Result(name, "C-integrity", False,
                              [("series", name, "no contract and not in NOT_CONTRACTED")]))

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
