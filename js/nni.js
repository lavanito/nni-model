// nni.js: the JavaScript port of nni_model (decomposition and DQR).
//
// What this file does
//   Reads build/model_input.json (written by `python -m nni_model.export`) and
//   works out, for one economy and year, the growth split of real NNI per head
//   (C1a, C2, C4, and C4a, C4b, C4c to 2023), the check term CHK, the flags,
//   and the DQR. It follows nni_model/decomposition.py and nni_model/dqr.py
//   line by line; tests/test_js_port.py checks both give the same numbers.
//
// Units: log points (change in the natural log, times 100).

const HIGH = 3, MEDIUM = 2, LOW = 1;
const NAMES = { 3: "High", 2: "Medium", 1: "Low" };
const LABELS = { 3: "Settled data, criteria met", 2: "Usable with the stated caveat", 1: "Indicative only" };

function logChange(oldValue, newValue) {
  return (Math.log(newValue) - Math.log(oldValue)) * 100;
}

class NNIDecomposition {
  constructor(input, economy) {
    this.input = input;
    this.economy = economy;
    this.values = input.values[economy] || {};
  }

  get(series, year) {
    const s = this.values[series];
    if (!s) return null;
    const v = s[String(year)];
    return v === undefined ? null : v;
  }

  years(series) {
    return Object.keys(this.values[series] || {}).map(Number).sort((a, b) => a - b);
  }

  // Adjusted NNI / GNI, and whether it was filled from the last published year.
  nniToGni(year) {
    const nni = this.get("NY.ADJ.NNTY.CD", year), gni = this.get("NY.GNP.MKTP.CD", year);
    if (nni !== null && gni !== null) return [nni / gni, false];
    const published = this.years("NY.ADJ.NNTY.CD").filter(
      (y) => y < year && this.get("NY.GNP.MKTP.CD", y) !== null);
    if (published.length === 0) return [null, false];
    const last = published[published.length - 1];
    return [this.get("NY.ADJ.NNTY.CD", last) / this.get("NY.GNP.MKTP.CD", last), true];
  }

  levels(year) {
    const gdp = this.get("NY.GDP.MKTP.CN", year), gdpReal = this.get("NY.GDP.MKTP.KN", year);
    const cons = this.get("NE.CON.PRVT.CN", year), consReal = this.get("NE.CON.PRVT.KD", year);
    const gni = this.get("NY.GNP.MKTP.CN", year), population = this.get("SP.POP.TOTL", year);
    if ([gdp, gdpReal, cons, consReal, gni, population].includes(null)) return null;
    const [ratio, filled] = this.nniToGni(year);
    if (ratio === null) return null;
    const nni = gni * ratio;
    const consumptionDeflator = cons / consReal;
    const nniPcUsd = this.get("NY.ADJ.NNTY.PC.CD", year), fx = this.get("PA.NUS.FCRF", year);
    return {
      nniToGdp: nni / gdp,
      gdpDeflator: gdp / gdpReal,
      consumptionDeflator,
      realGdpPerHead: gdpReal / population,
      realNniPerHead: nni / consumptionDeflator / population,
      direct: nniPcUsd !== null && fx !== null ? (nniPcUsd * fx) / consumptionDeflator : null,
      flags: filled ? ["estimated: NNI/GNI held at last published value"] : [],
      realGdp: gdpReal,
      personsEngaged: this.get("PWT.EMP", year),
      hoursPerPerson: this.get("PWT.AVH", year),
      population,
    };
  }

  year(year) {
    const a = this.levels(year - 1), b = this.levels(year);
    if (a === null || b === null) return null;
    const c1a = logChange(a.nniToGdp, b.nniToGdp);
    const c2 = logChange(a.gdpDeflator, b.gdpDeflator) - logChange(a.consumptionDeflator, b.consumptionDeflator);
    const c4 = logChange(a.realGdpPerHead, b.realGdpPerHead);
    const total = logChange(a.realNniPerHead, b.realNniPerHead);
    const chk = a.direct !== null && b.direct !== null
      ? logChange(a.direct, b.direct) - (c1a + c2 + c4) : null;
    const flags = [...b.flags];
    const breakText = this.input.breaks[`${this.economy}|${year}`];
    if (breakText) flags.push("break: " + breakText);
    const r = { economy: this.economy, year, c1a, c2, c4, total, chk, flags, c4a: null, c4b: null, c4c: null };
    if (![a.personsEngaged, b.personsEngaged, a.hoursPerPerson, b.hoursPerPerson].includes(null)) {
      const hoursA = a.personsEngaged * a.hoursPerPerson, hoursB = b.personsEngaged * b.hoursPerPerson;
      r.c4a = logChange(a.realGdp / hoursA, b.realGdp / hoursB);
      r.c4b = logChange(a.hoursPerPerson, b.hoursPerPerson);
      r.c4c = logChange(a.personsEngaged / a.population, b.personsEngaged / b.population);
    }
    return r;
  }

  run(from = 2001, to = 2025) {
    const out = [];
    for (let y = from; y <= to; y++) {
      const r = this.year(y);
      if (r !== null) out.push(r);
    }
    return out;
  }
}

// The S3 DQR rule; same steps and order as nni_model/dqr.py.
function rate(input, purpose, economies, flags = [], chk = null) {
  if (typeof economies === "string") economies = [economies];
  const candidates = [];
  for (const e of economies) {
    for (const series of input.inputs[purpose]) {
      const [band, reason] = input.ratings[series][purpose][e];
      candidates.push([band, `${e} ${series}: ${reason}`]);
    }
  }
  let [band, reason] = candidates.reduce((best, c) => (c[0] < best[0] ? c : best));
  for (const flag of flags) {
    const word = flag.split(":")[0].trim();
    const cap = input.flag_caps[word];
    if (word === "provisional") {
      if (band > LOW) { band -= 1; reason = `provisional (first release): one band below; ${reason}`; }
    } else if (cap !== undefined && cap !== null) {
      if (band > cap) { band = cap; reason = `${flag}; also ${reason}`; }
      else { reason = `${reason}; also ${flag}`; }
    }
  }
  if (chk !== null && Math.abs(chk) > 1 && band > LOW) {
    band = LOW;
    reason = `check term CHK = ${chk.toFixed(2)} points, above the 1-point cap`;
  }
  return { band, name: NAMES[band], label: LABELS[band], reason };
}

function rateDecomposition(input, result) {
  return rate(input, "P4", result.economy, result.flags.map((f) => f.split(":")[0]), result.chk);
}

// The figure as the page shows it: High one decimal, Medium whole number, Low "about".
function show(value, band) {
  if (band === HIGH) return value.toFixed(1);
  if (band === MEDIUM) return value.toFixed(0);
  return `about ${value.toFixed(0)}`;
}

module.exports = { NNIDecomposition, rate, rateDecomposition, show, logChange, HIGH, MEDIUM, LOW };
