"""Load WDI snapshots and build the euro area from its members.

What this file does
    Reads the long CSV files in data/wdi/ (one row per economy, series,
    year and value) into a Snapshot, and builds the euro area (code EA21)
    from the 21 member economies listed in the A2 data list.

Inputs
    data/wdi/wdi_latest_2026-10-08.csv            six economies (EMU lacks local-currency series)
    data/wdi/wdi_latest_2026-10-08_euro_members.csv  the 21 members

Outputs
    A Snapshot: values keyed by (economy, series, year), plus notes on how
    each built or filled value was made.
"""

import csv
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "wdi"

EURO_MEMBERS = ["AUT", "BEL", "BGR", "HRV", "CYP", "EST", "FIN", "FRA", "DEU", "GRC", "IRL",
                "ITA", "LVA", "LTU", "LUX", "MLT", "NLD", "PRT", "SVK", "SVN", "ESP"]


class Snapshot:
    """Values from one data edition, keyed by economy, series and year.

    Example:
        >>> s = Snapshot("WDI test")
        >>> s.set("GBR", "SP.POP.TOTL", 2024, 69281000.0)
        >>> s.get("GBR", "SP.POP.TOTL", 2024)
        69281000.0
        >>> s.get("GBR", "SP.POP.TOTL", 1990) is None
        True
    """

    def __init__(self, edition):
        self.edition = edition
        self.values = defaultdict(dict)   # (economy, series) -> {year: value}
        self.notes = []                   # how built values were made

    def set(self, economy, series, year, value):
        self.values[(economy, series)][year] = value

    def get(self, economy, series, year):
        return self.values.get((economy, series), {}).get(year)

    def years(self, economy, series):
        return sorted(self.values.get((economy, series), {}))


def load_csv(path, snapshot):
    """Add every non-blank value in a long CSV file to the snapshot."""
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["value"] == "":
                continue
            snapshot.set(row["economy"], row["series"], int(row["year"]), float(row["value"]))
    return snapshot


def total(snapshot, series, year, members=EURO_MEMBERS):
    """Sum of a series over the members, or None if any member lacks it."""
    values = [snapshot.get(m, series, year) for m in members]
    if any(v is None for v in values):
        return None
    return sum(values)


def chain_linked_volume(snapshot, nominal, real, years, base_year=2021):
    """Euro area volume, chain-linked at previous-year prices (ESA 2010, para. 10.20).

    Each year's volume growth = (sum over members of last year's nominal value
    times the member's own volume growth) / last year's nominal total.
    The index is scaled so the base year's volume equals its nominal value.
    """
    index = {years[0]: 1.0}
    for y in years[1:]:
        last_total = total(snapshot, nominal, y - 1)
        weighted = 0.0
        for m in EURO_MEMBERS:
            n_last = snapshot.get(m, nominal, y - 1)
            v_now, v_last = snapshot.get(m, real, y), snapshot.get(m, real, y - 1)
            if None in (n_last, v_now, v_last) or last_total is None or index.get(y - 1) is None:
                weighted = None
                break
            weighted += n_last * v_now / v_last
        index[y] = None if weighted is None else index[y - 1] * weighted / last_total
    scale = total(snapshot, nominal, base_year) / index[base_year]
    return {y: (None if index.get(y) is None else index[y] * scale) for y in years}


def build_euro_area(snapshot, years=range(2000, 2026), code="EA21"):
    """Add euro area series (code EA21) to the snapshot from its 21 members.

    Members' local-currency series are in euros for the whole period (earlier
    years at the fixed conversion rates), so nominal values are summed.
    Adjusted NNI: total GNI times the NNI/GNI ratio of the members that report
    NNI that year; the members missing and their share of GNI are noted.
    """
    years = list(years)
    for series in ["NY.GDP.MKTP.CN", "NY.GNP.MKTP.CN", "NE.CON.PRVT.CN",
                   "NY.GNP.MKTP.CD", "SP.POP.TOTL"]:
        for y in years:
            value = total(snapshot, series, y)
            if value is not None:
                snapshot.set(code, series, y, value)
    for nominal, real in [("NY.GDP.MKTP.CN", "NY.GDP.MKTP.KN"),
                          ("NE.CON.PRVT.CN", "NE.CON.PRVT.KD")]:
        for y, value in chain_linked_volume(snapshot, nominal, real, years).items():
            if value is not None:
                snapshot.set(code, real, y, value)
    for y in years:
        reporting = [m for m in EURO_MEMBERS
                     if snapshot.get(m, "NY.ADJ.NNTY.CD", y) is not None
                     and snapshot.get(m, "NY.GNP.MKTP.CD", y) is not None]
        gni_all = total(snapshot, "NY.GNP.MKTP.CD", y)
        if not reporting or gni_all is None:
            continue
        nni_rep = sum(snapshot.get(m, "NY.ADJ.NNTY.CD", y) for m in reporting)
        gni_rep = sum(snapshot.get(m, "NY.GNP.MKTP.CD", y) for m in reporting)
        nni = nni_rep / gni_rep * gni_all
        snapshot.set(code, "NY.ADJ.NNTY.CD", y, nni)
        snapshot.set(code, "NY.ADJ.NNTY.PC.CD", y, nni / snapshot.get(code, "SP.POP.TOTL", y))
        missing = [m for m in EURO_MEMBERS if m not in reporting]
        if missing:
            snapshot.notes.append(
                f"{code} {y}: NNI/GNI from members covering {gni_rep / gni_all:.2%} of GNI; "
                f"missing {', '.join(missing)}")
        fx = snapshot.get("DEU", "PA.NUS.FCRF", y)   # euros per dollar
        if fx is not None:
            snapshot.set(code, "PA.NUS.FCRF", y, fx)
    return snapshot


def latest_snapshot():
    """The latest WDI edition (8 October 2026) with the euro area built."""
    s = Snapshot("WDI 2026-10-08")
    load_csv(DATA / "wdi_latest_2026-10-08.csv", s)
    load_csv(DATA / "wdi_latest_2026-10-08_euro_members.csv", s)
    return build_euro_area(s)
