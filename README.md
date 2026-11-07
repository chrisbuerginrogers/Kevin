# Kevin

Browser tools for fisheries data, published with GitHub Pages. The landing page at https://chrisbuerginrogers.github.io/Kevin/ links to all three.

| Tool | Live page | What it does | How it calculates |
|---|---|---|---|
| **StockDB** | https://chrisbuerginrogers.github.io/Kevin/StockDB/ | Look up historical fish stocking records by water name or code | [StockDB/README.md](StockDB/README.md) |
| **WaTSS** | https://chrisbuerginrogers.github.io/Kevin/WaTSS/ | Summarize stream temperature logger data (MWAT, MWMT, M30AT, …) | [WaTSS/README.md](WaTSS/README.md) |
| **JakeOmatic** | https://chrisbuerginrogers.github.io/Kevin/JakeOMatic/ | Enter and summarize lake and stream fish surveys (CPUE, PSD, Wr, removal estimates) | [JakeOMatic/README.md](JakeOMatic/README.md) |

## StockDB

Search western stocking records from 1952–1999 (`StockDB/WestStock52-99mod.txt`, about 56,000 rows).

- **Lake / water name**: suggests matching waters as you type. Pick one to see its rows, or press Enter to show every water whose name contains the text.
- **Water code**: type a 5-digit code to see every row for it.
- Results appear in a scrollable table, with the row count and the total number of fish.

**Data notes.** Each water code normally has a single name. Abbreviations, typos and word-order variants were merged into one name per code (for example, LIME CR, LIME CREEK and LIME CRK became LIME CREEK). A few codes deliberately keep two names because the code itself looks miscoded:

| Code | Names |
|---|---|
| 19706 | "COLORADO R, SO FK" / ARAPAHO CREEK #1 |
| 65777 | "CAUSEWAY LAKE, LITTLE" / 13.5 ROAD POND #4 |
| 71186 | PURDY MESA RESERVOIR / HOLLENBECK RESERVOIR |
| 88535 | BEEF PASTURE BEAVER PONDS / CLEAR LK #2 (BEEFPASTURE) |
| 88612 | FISH LK / BLACK DIAMOND LAKE |
| 89373 | "DAVIES RES, BIG" / PORTER RES #1 & #2 |
| 89501 | SWEITZER LAKE / DELTA KIDS POND(SWEITZER) |

Years in the file are stored as two digits (`53`) and shown as `1953`. The original names are in the git history.

## WaTSS (Water Temperature Summary Software)

A browser version of WaTSS 3.0, built from the user manual (`WaTSS/WaTSSmanual3_04.pdf`; Rogers, K. B. 2015, Colorado Parks and Wildlife).

- **Input**: a HOBOware `.csv` export, or a WaTSS `.txt` export (two header lines, then `reading #, date time, temperature`). The page reads the units from the file header when it can, and detects 12-hour and 24-hour clocks automatically. Files never leave the browser.
- **Raw plot** (blue): cursor readout, zoom, pan, ◀ ▶ to step one reading at a time, and Reset.
- **Filtered plot** (green): Filter (Raw Data or Daily Max), then Averaging (daily, weekly, monthly, or a running average over a chosen window). The yellow (left) and orange (right) sliders choose the period to summarize.
- **Summary** (English by default, or Metric, from the raw readings between the sliders):
  - AveTemp: mean of the raw readings.
  - DailyMax: the highest 2-hour running average (Colorado standard).
  - DegDays: the sum of daily means above freezing.
  - MWAT: the warmest 7-day mean of daily means.
  - MWMT: the warmest 7-day mean of daily maxima.
  - M30AT: the warmest 30-day mean of daily means.
- **Export** saves the filtered series between the sliders as a WaTSS text file, which can be loaded again.
- **Download R code** saves a `.zip` with an R script and a tidy `.csv` (`series, datetime, month, days, segment, temp`). The script redraws both plots in ggplot2 with the current filter, sliders, zoom and Y limits. It is laid out like the code from [ggplotgui](https://shiny.gmw.rug.nl/ggplotgui/) (`df`, `theme_bw()`, plotly and `ggsave` lines). ggplotgui has no line graph, so the time-series code is written by hand. The script ends with how to open the same data in ggplotgui (`ggplotgui::ggplot_shiny(raw)`) for boxplots or histograms by month.
- **Try sample data** loads a synthetic 18-month hourly record for demonstration.

### How it's built

The page uses [PyScript](https://pyscript.net) (Pyodide), so the analysis runs as real Python in the browser:

| File | Role |
|---|---|
| `WaTSS/watss.py` | All analysis: parsing, filters, statistics, thresholds, export (WaTSS text and R/ggplot2 zip), sample data. Pure Python with no browser code. |
| `WaTSS/main.py` | A small PyScript bridge that keeps the loaded data and exposes `window.WaTSS` to the page |
| `WaTSS/index.html` | The interface only: layout, canvas plots, mouse and keyboard handling |

Because `watss.py` has no browser dependencies, you can test it with plain Python:

```bash
cd WaTSS
python3 -c "import watss; d = watss.parse(watss.sample_csv()); print(watss.compute_stats(d['t'], d['y'], 'F', d['dt'], d['t'][0], d['t'][-1])['metric'])"
```

## JakeOmatic

A fish survey data program, rewritten from JakeOmatic 3.0 as version 4.0. Like WaTSS, its calculations are in Python (`JakeOMatic/jakeomatic.py`) and run through PyScript, with `main.py` as the bridge and `index.html` as the interface only.

- **Lake survey**: survey info, effort hours (electrofishing, gill net, trap net), and a fish table. Statistics per species: CPUE (all fish and stock length and up), PSD, RSD-P, mean length and weight, and mean relative weight (Wr). Length-frequency and Wr charts.
- **Stream survey**: station length and width, a size filter, and two-pass fish records. Statistics: the Seber & Le Cren two-pass removal estimate with a 95% CI, then #/ha, kg/ha, #/km and kg/km.
- **Level II** tables for each survey, which can be exported as CSV.
- **Chapman-Petersen** mark-recapture calculator.
- **Species LUT**: standard-weight equations and length categories. You can edit them, add species, and the changes are saved in your browser.
- **Save / Open Survey** uses JSON files in the same layout as 3.0, so either version can open the other's files. **Export LF / Export Wr** produce CSV files. **Demo Data** loads a made-up survey.

**Changes from 3.0:**
- The fish **Count** field is now used. A row with count 5 counts as 5 fish everywhere.
- The two-pass removal variance now uses Seber & Le Cren (1967). The 3.0 formula underestimated it.
- Stream densities and biomass use the population estimate, and the size filter applies to all stream statistics.
- The statistic labelled "RSD-Q" in 3.0 actually computed RSD-P, so it's now labelled RSD-P.
- The charts show only the selected species.

## Running locally

The pages load their data and Python files with `fetch`, so opening them directly from disk (`file://`) won't work. Serve the repository instead:

```bash
python3 -m http.server 8000
# then open http://localhost:8000/ (or /StockDB/, /WaTSS/, /JakeOMatic/)
```

Pushing to `main` redeploys GitHub Pages within a minute or two.
