"""The JavaScript port gives the same numbers, flags and DQR as Python."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nni_model.data import latest_snapshot
from nni_model.decomposition import NNIDecomposition
from nni_model.dqr import HIGH, LOW, MEDIUM, Rating, cap_proxy, rate_decomposition, show
from nni_model.measures import real_nni_per_head_ppp
from nni_model.export import ECONOMIES, OUT, main

ROOT = Path(__file__).resolve().parent.parent


NEEDS_NODE = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")


def run_js():
    main()   # writes build/model_input.json
    return json.loads(subprocess.run(["node", str(ROOT / "js" / "run_all.js"), str(OUT)],
                                     capture_output=True, text=True, check=True).stdout)


@NEEDS_NODE
def test_js_matches_python():
    js = run_js()["decomposition"]
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


@NEEDS_NODE
def test_js_real_nni_per_head_in_international_dollars_matches_python():
    """Real NNI per head at constant 2021 PPPs, euro area household PPP built from members."""
    levels = run_js()["levels"]
    snapshot = latest_snapshot()
    assert len(levels) == 6 * 26
    found = 0
    for j in levels:
        value, flags = real_nni_per_head_ppp(snapshot, j["economy"], j["year"])
        assert (value is None) == (j["value"] is None), (j["economy"], j["year"])
        if value is not None:
            found += 1
            assert j["value"] == pytest.approx(value, rel=1e-12), (j["economy"], j["year"])
            assert j["flags"] == flags
    assert found > 120


@NEEDS_NODE
def test_js_digits_and_proxy_cap_match_python():
    js = run_js()
    python = [[show(v, b), show(v, b, rate=True), show(v, b, count=True)]
              for v in [0.04567, 2.4567, 1234.5, -31.456, 0.125, 2.5, -2.5, -0.04, 0.05, 1e-7, 40439.82450262]
              for b in [HIGH, MEDIUM, LOW]]
    assert js["shown"] == python
    p = cap_proxy(Rating(HIGH, "Settled data, criteria met", "C-measured: ok"))
    assert (js["proxy"]["band"], js["proxy"]["reason"]) == (p.band, p.reason) and p.band == LOW
