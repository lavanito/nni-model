"""DQR (data quality rating): the S3 rule, worked out by code.

What this file does
    Holds the S3 Layer A ratings as data (series x purpose x economy) and
    applies the S3 DQR rule:

        1. look up each input's rating for the answer's purpose and economy
        2. apply input flags (provisional: one band down; estimated, backfilled,
           forecast: at most Medium; outlier-suspect or break: Low)
        3. take the weakest link
        4. cap at Low if the check term CHK exceeds 1 percentage point
        5. comparisons take the weakest economy
        6. set the digits shown by band (decision 4 of build spec v2)

    The language model reports the band, its label and its reason; it never works them out.

Source
    S3 data quality statement, signed off by Lavan on 26 October 2026
    (statement per series). The consumption deflator's rating is not in S3;
    Lavan agreed on 26 October 2026 that it follows real GDP.
"""

from dataclasses import dataclass

HIGH, MEDIUM, LOW = 3, 2, 1
NAMES = {HIGH: "High", MEDIUM: "Medium", LOW: "Low"}
ECONOMIES = ["USA", "EA21", "GBR", "JPN", "CHN", "IND"]


def _all(band, reason, **overrides):
    """A rating for every economy, with named exceptions: {economy: (band, reason)}."""
    table = {e: (band, reason) for e in ECONOMIES}
    table.update(overrides)
    return table


CHINA_GDP = (MEDIUM, "C-concept: growth overstated by about 1.8 points a year, 2010-2016 "
                     "(Chen, Chen, Hsieh and Song, 2019); does not change the sign of growth")
INDIA_GDP = (LOW, "C-time: base year changed from 2011-12 to 2022-23 (MoSPI, Feb 2026); "
                  "nominal GDP about 3-4% lower; break in the series")
PPP_CN_IN = (LOW, "C-measured: PPPs extrapolated from the 2021 benchmark; wide error margins for China and India")
HOURS_CN_IN = (LOW, "C-measured: PWT hours rest on weak underlying data (TED, ILO modelled estimates), not direct observation")

# RATINGS[series][purpose][economy] = (band, reason); "-" = series not used for the purpose.
RATINGS = {
    "real_gdp": {
        p: _all(HIGH, "All criteria met", CHN=CHINA_GDP, IND=INDIA_GDP) for p in ("P1", "P3", "P4")
    },
    "gni_nni": {
        "P2": _all(HIGH, "All criteria met",
                   EA21=(MEDIUM, "C-concept: euro area total includes Ireland's multinational profits")),
        "P4": _all(MEDIUM, "C-concept: depreciation and depletion estimates differ in method between economies"),
    },
    "ppp": {
        "P2": _all(MEDIUM, "C-measured: 2022 onwards extrapolated from the ICP 2021 benchmark",
                   CHN=PPP_CN_IN, IND=PPP_CN_IN),
        "P3": _all(MEDIUM, "C-measured: 2022 onwards extrapolated from the ICP 2021 benchmark",
                   CHN=PPP_CN_IN, IND=PPP_CN_IN),
        "P4": _all(MEDIUM, "C-measured: PPP level from the ICP 2021 benchmark"),
    },
    "population": {
        p: _all(HIGH, "All criteria met",
                IND=(MEDIUM, "C-measured: last census 2011; error a few per cent, does not reverse the ranking"))
        for p in ("P2", "P4")
    },
    "employment": {
        "P3": _all(HIGH, "All criteria met",
                   CHN=(MEDIUM, "C-across: large informal employment; definitions differ"),
                   IND=(LOW, "C-time: employment source changes in 2019 (ETD to ILO official); "
                             "productivity growth across 2019 drops by about 9 points from the change alone")),
    },
    "hours": {
        p: _all(HIGH, "All criteria met", CHN=HOURS_CN_IN, IND=HOURS_CN_IN,
                EA21=(MEDIUM, "Estimated: built from PWT for 21 members; 0.5-1.8% below Eurostat's total hours"))
        for p in ("P2", "P3")
    },
    # Not in S3; agreed by Lavan on 26 October 2026: follows real GDP for P4.
    "consumption_deflator": {
        "P4": _all(HIGH, "All criteria met (rating follows real GDP; agreed 26 Oct 2026)",
                   CHN=CHINA_GDP, IND=INDIA_GDP),
    },
}

# Which inputs each purpose uses (S3 purposes table; build spec v2, component 4).
INPUTS = {
    "P1": ["real_gdp"],
    "P2": ["gni_nni", "ppp", "population"],
    "P3": ["real_gdp", "ppp", "employment", "hours"],
    "P4": ["real_gdp", "gni_nni", "ppp", "population", "consumption_deflator"],
}

FLAG_CAPS = {
    "published": None,
    "estimated": MEDIUM,
    "backfilled": MEDIUM,
    "forecast": MEDIUM,
    "outlier-suspect": LOW,
    "break": LOW,
}


@dataclass
class Rating:
    band: int
    label: str
    reason: str

    @property
    def name(self):
        return NAMES[self.band]


def rate(purpose, economies, flags=(), chk=None, inputs=None):
    """The DQR for an answer: band, label and the reason that set it.

    economies: one economy, or several for a comparison (weakest economy wins).
    flags: input flags on the values used, e.g. ["estimated"] or ["provisional"].

    Example (S3 worked example: "Is productivity higher in India or China?"):
        >>> r = rate("P3", ["IND", "CHN"])
        >>> r.name, r.reason.startswith("IND real_gdp")
        ('Low', True)
    """
    if isinstance(economies, str):
        economies = [economies]
    inputs = INPUTS[purpose] if inputs is None else inputs
    candidates = []
    for e in economies:
        for series in inputs:
            band, reason = RATINGS[series][purpose][e]
            candidates.append((band, f"{e} {series}: {reason}"))
    band, reason = min(candidates, key=lambda c: c[0])       # weakest link; first listed wins ties

    for flag in flags:
        word = flag.split(":")[0].strip()
        if word == "provisional":
            if band > LOW:
                band, reason = band - 1, f"provisional (first release): one band below; {reason}"
        elif FLAG_CAPS.get(word) is not None:
            if band > FLAG_CAPS[word]:
                band, reason = FLAG_CAPS[word], f"{flag}; also {reason}"
            else:
                reason = f"{reason}; also {flag}"       # the flag is always reported
    if chk is not None and abs(chk) > 1 and band > LOW:
        band, reason = LOW, f"check term CHK = {chk:.2f} points, above the 1-point cap"
    label = {HIGH: "Settled data, criteria met", MEDIUM: "Usable with the stated caveat",
             LOW: "Indicative only"}[band]
    return Rating(band, label, reason)


def show(value, band):
    """The figure as the page shows it, digits set by band (decision 4).

    Example:
        >>> show(2.4567, HIGH), show(2.4567, MEDIUM), show(2.4567, LOW)
        ('2.5', '2', 'about 2')
    """
    if band == HIGH:
        return f"{value:.1f}"
    if band == MEDIUM:
        return f"{value:.0f}"
    return f"about {value:.0f}"


def rate_decomposition(result):
    """DQR for one year of the P4 decomposition (a YearResult)."""
    flags = [f.split(":")[0] for f in result.flags]
    return rate("P4", result.economy, flags=flags, chk=result.chk)
