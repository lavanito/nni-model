"""The JavaScript port gives the same numbers, flags and DQR as Python."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nni_model.data import latest_snapshot
from nni_model.decomposition import NNIDecomposition
from nni_model.dqr import rate_decomposition
from nni_model.export import ECONOMIES, OUT, main

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_js_matches_python():
    main()   # writes build/model_input.json
    js = json.loads(subprocess.run(["node", str(ROOT / "js" / "run_all.js"), str(OUT)],
                                   capture_output=True, text=True, check=True).stdout)
    snapshot = latest_snapshot()
    python = [(r, rate_decomposition(r)) for e in ECONOMIES
              for r in NNIDecomposition(snapshot, e).run()]
    assert len(js) == len(python) > 120
    for j, (p, dqr) in zip(js, python):
        assert (j["economy"], j["year"]) == (p.economy, p.year)
        for part in ["c1a", "c2", "c4", "total", "chk", "c4a", "c4b", "c4c"]:
            pv, jv = getattr(p, part), j[part]
            assert (pv is None) == (jv is None), part
            if pv is not None:
                assert jv == pytest.approx(pv, abs=1e-9), (p.economy, p.year, part)
        assert j["flags"] == p.flags
        assert (j["dqr_band"], j["dqr_reason"]) == (dqr.band, dqr.reason)
