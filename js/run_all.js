// Prints, as JSON, every year's result and DQR for the six economies,
// so tests/test_js_port.py can compare with Python.
// Usage: node js/run_all.js build/model_input.json
const fs = require("fs");
const { NNIDecomposition, rateDecomposition } = require("./nni.js");

const input = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const out = [];
for (const economy of ["USA", "EA21", "GBR", "JPN", "CHN", "IND"]) {
  for (const r of new NNIDecomposition(input, economy).run()) {
    const dqr = rateDecomposition(input, r);
    out.push({ ...r, dqr_band: dqr.band, dqr_reason: dqr.reason });
  }
}
process.stdout.write(JSON.stringify(out));
