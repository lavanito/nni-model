"""Cross-checks: reported, not rated (S3 statement, Layer A).

What this file does
    Compares the model's inputs with a second source and reports the gaps,
    so the page can show them. A gap is "severe" only if, by the S3 band
    rule, it could reverse a ranking (levels) or change the sign of a growth
    rate. Severe gaps are reported too; nothing is hidden.

    1. Real output: growth, WDI (the model's source) against PWT 11.0 rgdpna
       (real GDP at constant national prices, the like-for-like series); level
       in 2021, WDI GDP at constant 2021 PPPs against PWT rgdpo. rgdpo's growth
       mixes in changes in relative prices, so it is used for the level only.
    2. Euro area hours: built from PWT for 21 members, against Eurostat's
       total hours worked (nama_10_a10_e, all industries, domestic concept).
    3. Euro area rank on real GDP per hour worked at PPP, 2023, with each hours source.
    4. Sign of euro area growth in real GDP per hour worked, 2023, with each hours source.

Not done: ILOSTAT modelled hours (A2 lists them; no download yet).
"""

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from nni_model.data import EURO_MEMBERS, Snapshot, latest_snapshot, load_csv

DATA = Path(__file__).resolve().parent.parent / "data"
SIX = ["USA", "EA21", "GBR", "JPN", "CHN", "IND"]
# Eurostat uses two-letter codes; Greece is EL.
EUROSTAT_CODES = {"AUT": "AT", "BEL": "BE", "BGR": "BG", "HRV": "HR", "CYP": "CY", "EST": "EE",
                  "FIN": "FI", "FRA": "FR", "DEU": "DE", "GRC": "EL", "IRL": "IE", "ITA": "IT",
                  "LVA": "LV", "LTU": "LT", "LUX": "LU", "MLT": "MT", "NLD": "NL", "PRT": "PT",
                  "SVK": "SK", "SVN": "SI", "ESP": "ES"}


def log_change(old, new):
    return (math.log(new) - math.log(old)) * 100


def load_inputs():
    s = latest_snapshot()
    load_csv(DATA / "wdi" / "wdi_latest_2026-10-08_euro_members_ppp.csv", s)
    with open(DATA / "pwt" / "pwt110_hours.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            # rgdpo and rgdpna are in millions of 2021 US$ (PWT 11.0 legend).
            if r["rgdpo"]:
                s.set(r["economy"], "PWT.RGDPO", int(r["year"]), float(r["rgdpo"]) * 1e6)
            if r["rgdpna"]:
                s.set(r["economy"], "PWT.RGDPNA", int(r["year"]), float(r["rgdpna"]) * 1e6)
    with open(DATA / "eurostat" / "nama_10_a10_e_emp_total.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s.set("ES:" + r["economy"], r["series"], int(r["year"]), float(r["value"]))
    for y in range(2000, 2026):
        for series in ["PWT.RGDPO", "NY.GDP.MKTP.PP.KD"]:   # rgdpna is not summable (national prices)
            values = [s.get(m, series, y) for m in EURO_MEMBERS]
            if None not in values:            # both in common international dollars, so summable
                s.set("EA21", series, y, sum(values))
        hours = [s.get("ES:" + EUROSTAT_CODES[m], "THS_HW", y) for m in EURO_MEMBERS]
        persons = [s.get("ES:" + EUROSTAT_CODES[m], "THS_PER", y) for m in EURO_MEMBERS]
        if None not in hours and None not in persons:
            s.set("EA21", "EUROSTAT.HOURS", y, sum(hours) * 1e3)
            s.set("EA21", "EUROSTAT.PERSONS", y, sum(persons) * 1e3)
    return s


@dataclass
class OutputGrowthCheck:
    economy: str
    mean_abs_gap: float        # log points, 2001-2023
    max_abs_gap: float
    max_year: int
    sign_differs: list         # years where WDI and PWT growth have opposite signs


def euro_rgdpna_growth(s, y):
    """Euro area rgdpna growth: members' growth weighted by last year's rgdpo (common prices)."""
    weights = [s.get(m, "PWT.RGDPO", y - 1) for m in EURO_MEMBERS]
    growth = [s.get(m, "PWT.RGDPNA", y) / s.get(m, "PWT.RGDPNA", y - 1) for m in EURO_MEMBERS]
    return math.log(sum(w * g for w, g in zip(weights, growth)) / sum(weights)) * 100


def output_growth(s, economy, years=range(2001, 2024)):
    """WDI real GDP growth against PWT rgdpna growth (log points)."""
    gaps, signs = [], []
    for y in years:
        w = log_change(s.get(economy, "NY.GDP.MKTP.KN", y - 1), s.get(economy, "NY.GDP.MKTP.KN", y))
        if economy == "EA21":
            p = euro_rgdpna_growth(s, y)
        else:
            p = log_change(s.get(economy, "PWT.RGDPNA", y - 1), s.get(economy, "PWT.RGDPNA", y))
        gaps.append((y, w - p))
        if w * p < 0:
            signs.append(y)
    worst = max(gaps, key=lambda g: abs(g[1]))
    return OutputGrowthCheck(economy, sum(abs(g) for _, g in gaps) / len(gaps),
                             abs(worst[1]), worst[0], signs)


def output_level_gap(s, economy, y=2021):
    """WDI GDP at constant 2021 PPPs / PWT rgdpo - 1, in % (both 2021 international $)."""
    return (s.get(economy, "NY.GDP.MKTP.PP.KD", y) / s.get(economy, "PWT.RGDPO", y) - 1) * 100


def pwt_hours(s, y):
    return s.get("EA21", "PWT.EMP", y) * s.get("EA21", "PWT.AVH", y)


def euro_hours_gap(s, years=range(2000, 2024)):
    """Per year: PWT total hours / Eurostat total hours - 1, and the same for persons (%)."""
    rows = []
    for y in years:
        hours = pwt_hours(s, y) / s.get("EA21", "EUROSTAT.HOURS", y) - 1
        persons = s.get("EA21", "PWT.EMP", y) / s.get("EA21", "EUROSTAT.PERSONS", y) - 1
        rows.append((y, hours * 100, persons * 100))
    return rows


def output_per_hour(s, economy, y, hours_source="PWT"):
    """Real GDP at constant 2021 PPPs per hour worked (WDI output, chosen hours)."""
    if hours_source == "Eurostat":
        hours = s.get(economy, "EUROSTAT.HOURS", y)
    else:
        hours = s.get(economy, "PWT.EMP", y) * s.get(economy, "PWT.AVH", y)
    return s.get(economy, "NY.GDP.MKTP.PP.KD", y) / hours


def ranking(s, y=2023, euro_hours="PWT"):
    values = {e: output_per_hour(s, e, y, euro_hours if e == "EA21" else "PWT") for e in SIX}
    return sorted(values, key=values.get, reverse=True), values


def euro_per_hour_growth(s, y=2023):
    """2023 growth in euro area real GDP per hour, with each hours source (log points)."""
    output = log_change(s.get("EA21", "NY.GDP.MKTP.KN", y - 1), s.get("EA21", "NY.GDP.MKTP.KN", y))
    pwt = output - log_change(pwt_hours(s, y - 1), pwt_hours(s, y))
    eurostat = output - log_change(s.get("EA21", "EUROSTAT.HOURS", y - 1), s.get("EA21", "EUROSTAT.HOURS", y))
    return output, pwt, eurostat


def report():
    """All four cross-checks, as plain-text lines for the page and the trace."""
    s = load_inputs()
    lines = ["1. Real output, WDI against PWT: growth gap against rgdpna, 2001-2023 (log points); "
             "level gap against rgdpo, 2021 (%)"]
    for e in SIX:
        c = output_growth(s, e)
        lines.append(f"   {e}: growth mean gap {c.mean_abs_gap:.2f}, largest {c.max_abs_gap:.2f} ({c.max_year}); "
                     f"opposite signs in {c.sign_differs or 'no year'}; level {output_level_gap(s, e):+.1f}%")
    gaps = euro_hours_gap(s)
    lines.append("2. Euro area hours, PWT against Eurostat (%): "
                 + "; ".join(f"{y} hours {h:+.1f}, persons {p:+.1f}" for y, h, p in gaps if y in (2000, 2019, 2022, 2023)))
    order_pwt, v_pwt = ranking(s)
    order_es, v_es = ranking(s, euro_hours="Eurostat")
    lines.append(f"3. Real GDP per hour at PPP, 2023 (int. $): order with PWT hours {order_pwt}; "
                 f"with Eurostat hours for the euro area {order_es}")
    output, pwt, eurostat = euro_per_hour_growth(s)
    lines.append(f"4. Euro area 2023: output {output:+.2f}; per hour {pwt:+.2f} (PWT hours), "
                 f"{eurostat:+.2f} (Eurostat hours)")
    return lines


if __name__ == "__main__":
    print("\n".join(report()))
