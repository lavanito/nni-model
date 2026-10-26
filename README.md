# nni-model

The model behind the AI readiness demonstrator. It works out real NNI per head at constant 2021 PPPs for six economies and splits each year's growth into parts that add up exactly.

Economies: United States, euro area (21 members, built here), United Kingdom, China, India, Japan.

## What it computes

Growth in real NNI per head, in log points, splits into:

| Part | What it shows |
|---|---|
| C1a Income gap | Depreciation, resource depletion, net income from abroad |
| C2 Deflator mix | Whether output prices rise faster than household prices |
| C4 Real GDP per head | Later split into output per hour worked, hours per worker and workers per person (needs PWT hours) |

The parts add up to the total exactly. The check term (CHK) compares the total with WDI's published adjusted NNI per head; it is zero where WDI converts at the official exchange rate.

The derivation, line by line, is in the project doc `claude/a4-identity-derivation.md` (agreed 26 October 2026).

## Flags

- **Estimated:** WDI's adjusted NNI ends in 2021 (United Kingdom: 2018). After that, NNI = GNI × the last published NNI/GNI. Recent years are needed, so the gap is filled and every filled year says so.
- **Break:** India's 2021 to 2022 change mixes the old and new GDP bases.

## Files

| Path | What it holds |
|---|---|
| `nni_model/data.py` | Loads WDI snapshots; builds the euro area from its members |
| `nni_model/decomposition.py` | The decomposition class |
| `nni_model/contracts.py` | Data contracts (S3 Layer B): C-complete, C-valid, C-integrity; a failing series is blocked |
| `nni_model/dqr.py` | DQR: S3 ratings as data, input flags, weakest link, CHK cap, digits by band |
| `tests/` | Exact sums, check term, flags, euro area build, contracts (pass and block), DQR worked examples |
| `data/wdi/` | WDI snapshots (see its README) |
| `data/pwt/` | PWT 11.0 hours and employment (see its README) |

## Run

```
python -m pytest --doctest-modules nni_model tests
```

Python 3.10 or later; pytest is the only package needed.

## Licence

Code: MIT, Lavan Mahadeva Ltd. Data: World Bank, World Development Indicators, CC BY 4.0.

## Glossary

- **Adjusted NNI:** gross national income minus consumption of fixed capital and natural resource depletion (WDI's definition).
- **Chain-linked volume:** a total built by linking each year's growth at the previous year's prices.
- **Log point:** the change in the natural log of a value, times 100; log points add exactly.
- **PPP (purchasing power parity):** a conversion rate that equalises what money buys across economies.
- **Vintage:** one dated release of the data.

## Links

- [World Bank API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392)
- [WDI archives](https://datatopics.worldbank.org/world-development-indicators/wdi-archives.html)
- [Textbook repository](https://github.com/lavanito/python-rag-textbook)
