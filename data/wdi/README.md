# WDI snapshots

Downloaded 26 October 2026 through the World Bank API (api.worldbank.org/v2), in the browser.

| File | Edition | Rows | Years |
|---|---|---|---|
| `wdi_latest_2026-10-08.csv` | WDI (source 2), last updated 8 October 2026; USA, EMU, GBR, CHN, IND, JPN; 17 series | 2,652 | 2000–2025 |
| `wdi_latest_2026-10-08_euro_members.csv` | Same edition; the 21 euro area members; 12 series | 6,552 | 2000–2025 |
| `wdi_archive_202403.csv` | WDI Database Archives (source 57), version 202403 ("2024 Mar"), the last edition before the ICP 2021 results (30 May 2024); six economies; 17 series | 2,550 | 2000–2024 |

Columns: economy, series, year, value (blank = not published).

WDI's euro area aggregate (EMU) has no local-currency series, so the model builds the euro area (EA21) from the members. WDI does not publish adjusted NNI in local currency (`NY.ADJ.NNTY.CN` does not exist).

Licence: CC BY 4.0, World Bank. Check each indicator's metadata for third-party restrictions.
