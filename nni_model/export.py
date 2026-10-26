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
from nni_model.data import latest_snapshot
from nni_model.decomposition import BREAKS
from nni_model.dqr import FLAG_CAPS, INPUTS, RATINGS

ECONOMIES = ["USA", "EA21", "GBR", "JPN", "CHN", "IND"]
SERIES = ["NY.GDP.MKTP.CN", "NY.GDP.MKTP.KN", "NE.CON.PRVT.CN", "NE.CON.PRVT.KD",
          "NY.GNP.MKTP.CN", "NY.GNP.MKTP.CD", "NY.ADJ.NNTY.CD", "NY.ADJ.NNTY.PC.CD",
          "PA.NUS.FCRF", "SP.POP.TOTL", "PWT.EMP", "PWT.AVH"]
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
    return {
        "edition": s.edition,
        "values": values,
        "breaks": {f"{e}|{y}": text for (e, y), text in BREAKS.items()},
        "ratings": RATINGS,
        "inputs": INPUTS,
        "flag_caps": FLAG_CAPS,
        "crosschecks": crosscheck_report(),
    }


def main():
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(model_input(), indent=1), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
