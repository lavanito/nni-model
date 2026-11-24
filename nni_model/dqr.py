"""DQR (data quality rating): the S3 rule, worked out by code.

What this file does
    Holds the S3 Layer A ratings as data (series x purpose x economy) and
    applies the S3 DQR rule:

        1. look up each input's rating for the answer's purpose and economy
        2. apply input flags (provisional: one band down; nowcast,
           forecast: at most Medium; outlier-suspect or break: Low)
        3. take the weakest link
        4. cap at Low if the check term CHK exceeds 1 percentage point
        5. comparisons take the weakest economy
        6. set the digits shown by band (decision 4 of build spec v2)

    The language model reports the band, its label and its reason; it never works them out.

Reasons
    Each reason that lowers a band names the S3 criterion, its CDDQ dimension
    and the underlying concept, then the fact: for example
    "C-measured (Lineage: Provenance): ...". CRITERIA lists the concepts
    each criterion may name (S3 draft 5, Criteria table).

Source
    S3 data quality statement, draft 5, signed off by Lavan on 21 November 2026
    (statement per series; criteria named after Myers, Data Quality
    Techniques, 2026). The consumption deflator's rating is not in S3;
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


# S3 draft 5: criterion -> (CDDQ dimension, underlying concepts it may name).
CRITERIA = {
    "C-coverage": ("Completeness", ["Existence"]),
    "C-concept": ("Accuracy", ["Agree with Real-world"]),
    "C-across": ("Consistency", ["Equivalence of Data"]),
    "C-time": ("Consistency", ["Temporal Consistency"]),
    "C-revision": ("Accuracy", ["Match to Agreed Source"]),
    "C-precision": ("Precision", ["Precision of Data Value", "Domain Precision", "Granularity"]),
    "C-measured": ("Lineage", ["Provenance", "Segment Documentation"]),
    "C-timely": ("Timeliness", ["Time Expectation for Availability"]),
    "C-currency": ("Currency", ["Current with World it Models"]),
    "C-representation": ("Representation", ["Metadata Availability", "Includes Measurement Units"]),
}
MET = "All criteria met"


def why(criterion, concept, fact):
    """A rating reason that names the criterion, dimension and underlying concept.

    Example:
        >>> why("C-time", "Temporal Consistency", "break in 2019")
        'C-time (Consistency: Temporal Consistency): break in 2019'
    """
    dimension, concepts = CRITERIA[criterion]
    if concept not in concepts:
        raise ValueError(f"{concept} is not an underlying concept of {criterion}")
    return f"{criterion} ({dimension}: {concept}): {fact}"


CHINA_GDP = (MEDIUM, why("C-concept", "Agree with Real-world",
                         "growth overstated by about 1.8 points a year, 2010-2016 "
                         "(Chen, Chen, Hsieh and Song, 2019); does not change the sign of growth"))
INDIA_GDP = (LOW, why("C-time", "Temporal Consistency",
                      "base year changed from 2011-12 to 2022-23 (MoSPI, Feb 2026); "
                      "nominal GDP about 3-4% lower; break in the series"))
PPP_CN_IN = (LOW, why("C-measured", "Segment Documentation",
                      "PPPs extrapolated from the 2021 benchmark; wide error margins for China and India"))
HOURS_CN_IN = (LOW, why("C-measured", "Provenance",
                        "PWT hours come from weak underlying data (TED, ILO modelled estimates), "
                        "not direct observation"))

PPP_EXTRAPOLATED = why("C-measured", "Segment Documentation",
                       "2022 onwards extrapolated from the ICP 2021 benchmark")

# RATINGS[series][purpose][economy] = (band, reason); "-" = series not used for the purpose.
RATINGS = {
    "real_gdp": {
        p: _all(HIGH, MET, CHN=CHINA_GDP, IND=INDIA_GDP) for p in ("P1", "P3", "P4")
    },
    "gni_nni": {
        "P2": _all(HIGH, MET,
                   EA21=(MEDIUM, why("C-concept", "Agree with Real-world",
                                     "euro area total includes Ireland's multinational profits"))),
        "P4": _all(MEDIUM, why("C-measured", "Segment Documentation",
                               "depreciation and depletion are estimated, not observed")),
    },
    "ppp": {
        "P2": _all(MEDIUM, PPP_EXTRAPOLATED, CHN=PPP_CN_IN, IND=PPP_CN_IN),
        "P3": _all(MEDIUM, PPP_EXTRAPOLATED, CHN=PPP_CN_IN, IND=PPP_CN_IN),
        "P4": _all(MEDIUM, why("C-measured", "Provenance", "PPP level from the ICP 2021 benchmark")),
    },
    "population": {
        p: _all(HIGH, MET,
                IND=(MEDIUM, why("C-measured", "Segment Documentation",
                                 "projected from the last census, 2011; error a few per cent, does not reverse the ranking")))
        for p in ("P2", "P4")
    },
    "employment": {
        "P3": _all(HIGH, MET,
                   CHN=(MEDIUM, why("C-across", "Equivalence of Data",
                                    "large informal employment; definitions differ")),
                   IND=(LOW, why("C-time", "Temporal Consistency",
                                 "employment source changes in 2019 (ETD to ILO official); "
                                 "productivity growth across 2019 drops by about 9 points "
                                 "from the change alone"))),
    },
    "hours": {
        p: _all(HIGH, MET, CHN=HOURS_CN_IN, IND=HOURS_CN_IN,
                EA21=(MEDIUM, why("C-measured", "Segment Documentation",
                                  "estimated: built from PWT for 21 members; "
                                  "0.5-1.8% below Eurostat's total hours")))
        for p in ("P2", "P3")
    },
    # Not in S3; agreed by Lavan on 26 October 2026: follows real GDP for P4.
    "consumption_deflator": {
        "P4": _all(HIGH, MET + " (rating follows real GDP; agreed 26 Oct 2026)",
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
    "nowcast": MEDIUM,      # replaced "estimated" and "backfilled" (Lavan, 22 Nov 2026)
    "forecast": MEDIUM,
    "outlier-suspect": LOW,
    "break": LOW,
}

# S3 draft 5, DQR rule step 2: the test behind the outlier-suspect flag.
FLAG_CONCEPTS = {"outlier-suspect": "Validity: Values in Specified Range"}


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
    flags: input flags on the values used, e.g. ["nowcast"] or ["provisional"].

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
            if word in FLAG_CONCEPTS:
                flag = f"{flag} ({FLAG_CONCEPTS[word]})"
            if band > FLAG_CAPS[word]:
                band, reason = FLAG_CAPS[word], f"{flag}; also {reason}"
            else:
                reason = f"{reason}; also {flag}"       # the flag is always reported
    if chk is not None and abs(chk) > 1 and band > LOW:
        band, reason = LOW, f"check term CHK = {chk:.2f} points, above the 1-point cap"
    label = {HIGH: "Settled data, criteria met", MEDIUM: "Usable with the stated caveat",
             LOW: "Indicative only"}[band]
    return Rating(band, label, reason)


# Rates (log points, per cent) get one more decimal place than levels:
# High 2, Medium 1, Low "about" and 1 (the horizontal domain expert, 7 November 2026).
RATE_DECIMALS = {HIGH: 2, MEDIUM: 1, LOW: 1}


def show(value, band, rate=False, count=False):
    """The figure as the page shows it, digits set by band (decision 4).

    Levels: High one decimal, Medium whole, Low "about" and whole. Rates
    (log points, per cent) one more decimal than levels. Counts, such as
    population, always whole. A Low band always says "about".

    Example:
        >>> show(2.4567, HIGH), show(2.4567, MEDIUM), show(2.4567, LOW)
        ('2.5', '2', 'about 2')
        >>> show(2.4567, HIGH, rate=True), show(2.4567, LOW, rate=True), show(1234.5, HIGH, count=True)
        ('2.46', 'about 2.5', '1234')
    """
    if rate:
        text = f"{value:.{RATE_DECIMALS[band]}f}"
    elif count:
        text = f"{value:.0f}"
    elif band == HIGH:
        return f"{value:.1f}"
    elif band == MEDIUM:
        return f"{value:.0f}"
    else:
        return f"about {value:.0f}"
    return f"about {text}" if band == LOW else text


def cap_proxy(rating):
    """A proxy figure is rated at most Low (the horizontal domain expert, 7 November 2026).

    Example:
        >>> cap_proxy(Rating(HIGH, "x", "C-measured: ok")).band == LOW
        True
    """
    return Rating(LOW, "Indicative only", f"proxy, rated at most Low; also {rating.reason}")


def rate_decomposition(result):
    """DQR for one year of the P4 decomposition (a YearResult)."""
    flags = [f.split(":")[0] for f in result.flags]
    return rate("P4", result.economy, flags=flags, chk=result.chk)
