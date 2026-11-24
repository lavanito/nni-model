"""Write the JSON the page loads: data for the six economies, breaks and DQR tables.

What this file does
    Exports, from the Python model, everything the JavaScript port needs,
    so both read the same numbers and the same rating tables:
    build/model_input.json.

Run
    python -m nni_model.export
"""

import json
from pathlib import Path

from nni_model.contracts import blocked, check
from nni_model.crosschecks import report as crosscheck_report
from nni_model.data import EURO_MEMBERS, latest_snapshot
from nni_model.decomposition import BREAKS
from nni_model.dqr import FLAG_CAPS, FLAG_CONCEPTS, INPUTS, RATINGS

ECONOMIES = ["USA", "EA21", "GBR", "JPN", "CHN", "IND"]
SERIES = ["NY.GDP.MKTP.CN", "NY.GDP.MKTP.KN", "NE.CON.PRVT.CN", "NE.CON.PRVT.KD",
          "NY.GNP.MKTP.CN", "NY.GNP.MKTP.CD", "NY.ADJ.NNTY.CD", "NY.ADJ.NNTY.PC.CD",
          "PA.NUS.FCRF", "SP.POP.TOTL", "PWT.EMP", "PWT.AVH", "PA.NUS.PRVT.PP"]
# The euro area's household PPP is built from its members (nni_model/measures.py).
MEMBER_SERIES = ["NE.CON.PRVT.CN", "PA.NUS.PRVT.PP"]
OUT = Path(__file__).resolve().parent.parent / "build" / "model_input.json"


def model_input():
    stopped = blocked(check())
    if stopped:
        raise RuntimeError(f"Contracts failed; blocked series: {stopped}")
    s = latest_snapshot()
    values = {}
    for e in ECONOMIES:
        for series in SERIES:
            for y in s.years(e, series):
                values.setdefault(e, {}).setdefault(series, {})[str(y)] = s.get(e, series, y)
    for m in EURO_MEMBERS:
        for series in MEMBER_SERIES:
            for y in s.years(m, series):
                values.setdefault(m, {}).setdefault(series, {})[str(y)] = s.get(m, series, y)
    return {
        "edition": s.edition,
        "euro_members": EURO_MEMBERS,
        "values": values,
        "breaks": {f"{e}|{y}": text for (e, y), text in BREAKS.items()},
        "ratings": RATINGS,
        "inputs": INPUTS,
        "flag_caps": FLAG_CAPS,
        "flag_concepts": FLAG_CONCEPTS,
        "crosschecks": crosscheck_report(),
    }


def main():
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(model_input(), indent=1), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
