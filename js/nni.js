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
      flags: filled ? ["nowcast: NNI/GNI held at last published value"] : [],
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
  for (let flag of flags) {
    const word = flag.split(":")[0].trim();
    const cap = input.flag_caps[word];
    if (word === "provisional") {
      if (band > LOW) { band -= 1; reason = `provisional (first release): one band below; ${reason}`; }
    } else if (cap !== undefined && cap !== null) {
      if (input.flag_concepts[word]) flag = `${flag} (${input.flag_concepts[word]})`;
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

// The figure as the page shows it; same rules as nni_model/dqr.py show().
// Levels: High one decimal, Medium whole number, Low "about". Rates one more
// decimal than levels (High 2, Medium 1, Low "about" and 1). Counts whole.
const RATE_DECIMALS = { 3: 2, 2: 1, 1: 1 };

// Fixed decimals rounded as Python's format does: on the exact decimal value of
// the number, ties to even (1234.5 -> "1234"). JavaScript's toFixed rounds ties
// away from zero, so it is used only to get the exact digits.
function fixed(value, decimals) {
  const [whole, fraction] = Math.abs(value).toFixed(100).split(".");
  const rest = fraction.slice(decimals);
  let digits = BigInt(whole + fraction.slice(0, decimals));
  if (rest[0] > "5" || (rest[0] === "5" && /[1-9]/.test(rest.slice(1)))) digits += 1n;
  else if (rest[0] === "5" && digits % 2n === 1n) digits += 1n;
  const text = digits.toString().padStart(decimals + 1, "0");
  const out = decimals ? `${text.slice(0, -decimals)}.${text.slice(-decimals)}` : text;
  return value < 0 || Object.is(value, -0) ? `-${out}` : out;
}

function show(value, band, { rate = false, count = false } = {}) {
  let text;
  if (rate) text = fixed(value, RATE_DECIMALS[band]);
  else if (count) text = fixed(value, 0);
  else if (band === HIGH) return fixed(value, 1);
  else if (band === MEDIUM) return fixed(value, 0);
  else return `about ${fixed(value, 0)}`;
  return band === LOW ? `about ${text}` : text;
}

// A proxy figure is rated at most Low; same as nni_model/dqr.py cap_proxy().
function capProxy(rating) {
  return { band: LOW, name: NAMES[LOW], label: LABELS[LOW],
           reason: `proxy, rated at most Low; also ${rating.reason}` };
}

// Household-consumption PPP; for EA21 built from its members (nni_model/measures.py).
function householdPPP(input, code, year) {
  const get = (e, series) => {
    const v = ((input.values[e] || {})[series] || {})[String(year)];
    return v === undefined ? null : v;
  };
  if (code !== "EA21") return get(code, "PA.NUS.PRVT.PP");
  let euros = 0, dollars = 0;
  for (const m of input.euro_members) {
    const cons = get(m, "NE.CON.PRVT.CN"), ppp = get(m, "PA.NUS.PRVT.PP");
    if (cons === null || ppp === null) return null;
    euros += cons;
    dollars += cons / ppp;
  }
  return euros / dollars;
}

// Real NNI per head in constant 2021 international dollars, and its flags.
function realNniPerHeadPPP(input, code, year, base = 2021) {
  const model = new NNIDecomposition(input, code);
  const atBase = model.levels(base), now = model.levels(year);
  const ppp = householdPPP(input, code, base), gdp = model.get("NY.GDP.MKTP.CN", base);
  if (atBase === null || now === null || ppp === null || gdp === null) return [null, []];
  const baseLevel = atBase.nniToGdp * gdp / ppp / atBase.population;
  return [baseLevel * now.realNniPerHead / atBase.realNniPerHead, [...now.flags]];
}

module.exports = { NNIDecomposition, rate, rateDecomposition, show, capProxy, householdPPP,
                   realNniPerHeadPPP, fixed, logChange, HIGH, MEDIUM, LOW };
