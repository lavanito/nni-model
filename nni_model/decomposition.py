"""Real NNI per head at constant 2021 PPPs, and its growth split into parts.

What this file does
    For one economy and one data snapshot, works out real NNI per head and
    splits each year's growth into parts that add up exactly (identity agreed
    by Lavan on 26 October 2026; claude/a4-identity-derivation.md):

        growth = C1a income gap + C2 deflator mix + C4 real GDP per head

    C4 splits further into output per hour worked (C4a), hours per worker
    (C4b) and workers per person (C4c), from PWT 11.0 hours and persons
    engaged (to 2023; later years show C4 unsplit).
    CHK compares with WDI's published adjusted NNI per head.

Inputs
    A Snapshot (nni_model/data.py).

Outputs
    One YearResult per year: the parts in log points, the total, CHK, and the
    input flags and breaks that apply.

Units
    Log points: the change in the natural log of a value, times 100.
"""

import math
from dataclasses import dataclass, field

# Known breaks in a series (criterion C-time in the S3 statement).
BREAKS = {
    ("IND", 2019): "PWT employment for India changes source in 2019 (ETD to ILO official): "
                   "persons engaged rise 9.4%, so C4a and C4c shift; their sum is unaffected.",
    ("IND", 2022): "India's GDP rebased to 2022-23 (MoSPI, 27 Feb 2026): WDI's nominal "
                   "values are on the new base from 2022 and on the old base for 2021.",
}


def log_change(old, new):
    """Change in the natural log, times 100.

    Example:
        >>> round(log_change(100.0, 105.0), 2)
        4.88
    """
    return (math.log(new) - math.log(old)) * 100


@dataclass
class Levels:
    """The values one year contributes to the identity."""
    nni_to_gdp: float          # adjusted NNI / GDP, both in local currency
    gdp_deflator: float        # P_G = GDP current / GDP constant
    consumption_deflator: float  # P_C = consumption current / consumption constant
    real_gdp_per_head: float
    real_nni_per_head: float   # NNI / (P_C x population), constant prices
    direct: float = None       # from WDI's published NNI per head, for CHK
    real_gdp: float = None
    persons_engaged: float = None   # PWT emp
    hours_per_person: float = None  # PWT avh
    population: float = None
    flags: list = field(default_factory=list)


@dataclass
class YearResult:
    economy: str
    year: int
    c1a: float
    c2: float
    c4: float
    total: float
    chk: float = None
    flags: list = field(default_factory=list)
    c4a: float = None   # output per hour worked
    c4b: float = None   # hours per worker
    c4c: float = None   # workers per person

    @property
    def parts_sum(self):
        return self.c1a + self.c2 + self.c4


class NNIDecomposition:
    """Growth in real NNI per head, split into parts that add up exactly.

    Example (made-up data, two years):
        >>> from nni_model.data import Snapshot
        >>> s = Snapshot("example")
        >>> for y, k in [(2020, 1.0), (2021, 1.05)]:
        ...     for code, v in [("NY.GDP.MKTP.CN", 100 * k * k), ("NY.GDP.MKTP.KN", 100 * k),
        ...                     ("NE.CON.PRVT.CN", 60 * k * k), ("NE.CON.PRVT.KD", 60 * k),
        ...                     ("NY.GNP.MKTP.CN", 99 * k * k), ("NY.GNP.MKTP.CD", 99 * k * k),
        ...                     ("NY.ADJ.NNTY.CD", 85 * k * k), ("SP.POP.TOTL", 10.0)]:
        ...         s.set("XXX", code, y, v)
        >>> r = NNIDecomposition(s, "XXX").year(2021)
        >>> round(r.total, 2), round(r.parts_sum, 2)
        (4.88, 4.88)
    """

    def __init__(self, snapshot, economy):
        self.snapshot = snapshot
        self.economy = economy

    def _get(self, series, year):
        return self.snapshot.get(self.economy, series, year)

    def nni_to_gni(self, year):
        """Adjusted NNI / GNI for the year, and whether it was filled.

        Both values are in dollars at the same conversion rate, so the rate
        cancels. After the last published year, the ratio is held at its last
        published value and the year is flagged "estimated".
        """
        nni, gni = self._get("NY.ADJ.NNTY.CD", year), self._get("NY.GNP.MKTP.CD", year)
        if nni is not None and gni is not None:
            return nni / gni, False
        published = [y for y in self.snapshot.years(self.economy, "NY.ADJ.NNTY.CD")
                     if y < year and self._get("NY.GNP.MKTP.CD", y) is not None]
        if not published:
            return None, False
        last = published[-1]
        return self._get("NY.ADJ.NNTY.CD", last) / self._get("NY.GNP.MKTP.CD", last), True

    def levels(self, year):
        """Levels for one year, or None if a required series is missing."""
        gdp = self._get("NY.GDP.MKTP.CN", year)
        gdp_real = self._get("NY.GDP.MKTP.KN", year)
        cons = self._get("NE.CON.PRVT.CN", year)
        cons_real = self._get("NE.CON.PRVT.KD", year)
        gni = self._get("NY.GNP.MKTP.CN", year)
        population = self._get("SP.POP.TOTL", year)
        if None in (gdp, gdp_real, cons, cons_real, gni, population):
            return None
        ratio, filled = self.nni_to_gni(year)
        if ratio is None:
            return None
        nni = gni * ratio                         # adjusted NNI, local currency
        consumption_deflator = cons / cons_real
        flags = ["estimated: NNI/GNI held at last published value"] if filled else []
        direct = None
        nni_pc_usd, fx = self._get("NY.ADJ.NNTY.PC.CD", year), self._get("PA.NUS.FCRF", year)
        if nni_pc_usd is not None and fx is not None:
            direct = nni_pc_usd * fx / consumption_deflator
        return Levels(
            nni_to_gdp=nni / gdp,
            gdp_deflator=gdp / gdp_real,
            consumption_deflator=consumption_deflator,
            real_gdp_per_head=gdp_real / population,
            real_nni_per_head=nni / consumption_deflator / population,
            direct=direct,
            flags=flags,
            real_gdp=gdp_real,
            persons_engaged=self._get("PWT.EMP", year),
            hours_per_person=self._get("PWT.AVH", year),
            population=population,
        )

    def year(self, year):
        """The split of growth from year - 1 to year, or None if data is missing."""
        old, new = self.levels(year - 1), self.levels(year)
        if old is None or new is None:
            return None
        c1a = log_change(old.nni_to_gdp, new.nni_to_gdp)
        c2 = (log_change(old.gdp_deflator, new.gdp_deflator)
              - log_change(old.consumption_deflator, new.consumption_deflator))
        c4 = log_change(old.real_gdp_per_head, new.real_gdp_per_head)
        total = log_change(old.real_nni_per_head, new.real_nni_per_head)
        chk = None
        if old.direct is not None and new.direct is not None:
            chk = log_change(old.direct, new.direct) - (c1a + c2 + c4)
        flags = list(new.flags)
        if (self.economy, year) in BREAKS:
            flags.append("break: " + BREAKS[(self.economy, year)])
        result = YearResult(self.economy, year, c1a, c2, c4, total, chk, flags)
        if None not in (old.persons_engaged, new.persons_engaged,
                        old.hours_per_person, new.hours_per_person):
            hours_old = old.persons_engaged * old.hours_per_person
            hours_new = new.persons_engaged * new.hours_per_person
            result.c4a = log_change(old.real_gdp / hours_old, new.real_gdp / hours_new)
            result.c4b = log_change(old.hours_per_person, new.hours_per_person)
            result.c4c = log_change(old.persons_engaged / old.population,
                                    new.persons_engaged / new.population)
        return result

    def run(self, years=range(2001, 2026)):
        """Every year with data, in order."""
        results = []
        for y in years:
            r = self.year(y)
            if r is not None:
                results.append(r)
        return results
