"""Measures from the NNI model in international dollars (gate A5, from Chapter 13).

What this file does
    Moves two calculations from the textbook's Chapter 13 into the model, so
    the page's JavaScript port can repeat them:

    - household_ppp: the household-consumption PPP factor (PA.NUS.PRVT.PP);
      for the euro area, members' household consumption in euros divided by
      the same in international dollars;
    - real_nni_per_head_ppp: real NNI per head in constant 2021
      international dollars. In 2021: NNI in local currency / the 2021
      household PPP / population. Other years: the 2021 level moved by the
      model's own real NNI per head, so growth matches the decomposition
      exactly (method approved by the vertical domain expert, 7 November 2026).

    js/nni.js repeats both; tests/test_js_port.py checks they agree.

Source
    The textbook, ragbook/ch13_model_tool.py (functions of the same names).
"""

from nni_model.data import EURO_MEMBERS
from nni_model.decomposition import NNIDecomposition

BASE_YEAR = 2021


def household_ppp(s, code, year):
    """The household-consumption PPP factor, local currency per international dollar.

    For the euro area (EA21): the sum of members' household consumption in
    euros over the sum of the same in international dollars. None if any
    part is missing.
    """
    if code != "EA21":
        return s.get(code, "PA.NUS.PRVT.PP", year)
    euros, dollars = 0.0, 0.0
    for member in EURO_MEMBERS:
        cons, ppp = s.get(member, "NE.CON.PRVT.CN", year), s.get(member, "PA.NUS.PRVT.PP", year)
        if None in (cons, ppp):
            return None
        euros += cons
        dollars += cons / ppp
    return euros / dollars


def real_nni_per_head_ppp(s, code, year, base=BASE_YEAR):
    """Real NNI per head in constant 2021 international dollars, and its flags.

    Returns (value, flags); value is None if an input is missing.
    """
    model = NNIDecomposition(s, code)
    at_base, now = model.levels(base), model.levels(year)
    ppp, gdp = household_ppp(s, code, base), s.get(code, "NY.GDP.MKTP.CN", base)
    if None in (at_base, now, ppp, gdp):
        return None, []
    base_level = at_base.nni_to_gdp * gdp / ppp / at_base.population
    return base_level * now.real_nni_per_head / at_base.real_nni_per_head, list(now.flags)
