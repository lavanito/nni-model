// Prints, as JSON, every year's result and DQR for the six economies,
// so tests/test_js_port.py can compare with Python.
// Usage: node js/run_all.js build/model_input.json
const fs = require("fs");
const { NNIDecomposition, rateDecomposition, show, capProxy, realNniPerHeadPPP } = require("./nni.js");

const input = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const out = [];
for (const economy of ["USA", "EA21", "GBR", "JPN", "CHN", "IND"]) {
  for (const r of new NNIDecomposition(input, economy).run()) {
    const dqr = rateDecomposition(input, r);
    out.push({ ...r, dqr_band: dqr.band, dqr_reason: dqr.reason });
  }
}
// Real NNI per head in international dollars, every economy and year.
const levels = [];
for (const economy of ["USA", "EA21", "GBR", "JPN", "CHN", "IND"]) {
  for (let year = 2000; year <= 2025; year++) {
    const [value, flags] = realNniPerHeadPPP(input, economy, year);
    levels.push({ economy, year, value, flags });
  }
}
// Digits: the same sample values in every band and kind, ties and signs included.
const SAMPLES = [0.04567, 2.4567, 1234.5, -31.456, 0.125, 2.5, -2.5, -0.04, 0.05, 1e-7, 40439.82450262];
const shown = [];
for (const value of SAMPLES) {
  for (const band of [3, 2, 1]) {
    shown.push([show(value, band), show(value, band, { rate: true }), show(value, band, { count: true })]);
  }
}
const proxy = capProxy({ band: 3, reason: "C-measured: ok" });
process.stdout.write(JSON.stringify({ decomposition: out, levels, shown, proxy }));
