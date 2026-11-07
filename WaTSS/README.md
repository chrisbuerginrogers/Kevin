# WaTSS: how the calculations work

WaTSS (Water Temperature Summary Software) summarizes stream temperature logger records. This page explains each step from reading the file to the summary table. All of the code is in [`watss.py`](watss.py), and the function names below refer to it.

Live page: https://chrisbuerginrogers.github.io/Kevin/WaTSS/
Original method: Rogers, K. B. 2015. *User manual for WaTSS 3.0* ([`WaTSSmanual3_04.pdf`](WaTSSmanual3_04.pdf)).

## 1. Reading the file (`parse`)

- **Columns.** Header lines are skipped. The first row that has a date/time followed by a number decides the layout: that column is the time stamp, and the next column is the temperature. This works for HOBOware `.csv` exports and for WaTSS `.txt` exports.
- **Dates.** Dates are read as month/day/year, unless the year comes first (`2013-06-02`). Two-digit years below 70 are read as 20xx, and the rest as 19xx. If the time ends in AM or PM it's read as a 12-hour clock, otherwise as a 24-hour clock.
- **Clock time.** Times are kept as the logger recorded them, with no time zone or daylight-saving changes. So a "day" in WaTSS is midnight to midnight on the logger's clock.
- **Units.** If the first header lines name the unit (`°F`, `°C`, `Temp, °F`), that unit is used. Otherwise you choose it from the **Source units** menu.
- **Reading interval** (`typical_interval`). The median gap between readings, taken from the first 2,000 gaps. For hourly data this is 1 hour. It's used by the DailyMax rule below and to break plot lines at gaps.

Readings are sorted by time. Rows without a valid date and number are skipped.

## 2. The filtered (green) plot (`filter_series`)

The green plot applies two settings in order: **Filter**, then **Averaging**.

**Filter**

| Setting | What it does |
|---|---|
| Raw Data | Uses every reading |
| Daily Max | The highest reading on each calendar day, plotted at noon |

**Averaging**

| Setting | What it does |
|---|---|
| None | No averaging |
| Daily | Mean of all points on each calendar day, plotted at noon |
| Weekly | Mean of consecutive 7-day blocks that start on the first day of data, plotted at noon on day 4 of each block |
| Monthly | Mean of all points in each calendar month, plotted at noon on the 15th |
| Running | Centred running mean over *w* consecutive points (the window box) |

The running average of point *i* is the mean of the *w* points centred on it:

```math
\bar{y}_i = \frac{1}{w}\sum_{k=i-h}^{i-h+w-1} y_k, \qquad h = \left\lfloor \frac{w-1}{2} \right\rfloor
```

The first and last *h* points are dropped because there isn't a full window around them. For example, a window of 3 on `10, 12, 14, 16, 18` gives `12, 14, 16`.

The window counts **points**, not hours. On hourly Raw Data, a window of 24 is a running daily mean. On Daily Max, a window of 7 is a 7-day running mean of daily maxima (the curve behind MWMT).

**The filter only changes the green plot.** The summary statistics always use the raw readings.

## 3. Summary statistics (`compute_stats`)

The summary uses every **raw** reading between the yellow (left) and orange (right) sliders, ends included. Readings are converted to °C first:

```math
T_{°C} = \frac{T_{°F} - 32}{1.8}
```

### Daily means and maxima

Each calendar day with at least one reading gets:

- **daily mean**: the mean of that day's readings
- **daily max**: that day's highest reading

Days with only some readings (the first and last day, or a day the logger was pulled) still count, using whatever readings they have. If you want only complete days, set the sliders to midnight.

### The statistics

| Statistic | How it's calculated |
|---|---|
| **AveTemp** | Mean of all raw readings between the sliders |
| **DailyMax** | The highest **2-hour running average** of the raw readings (Colorado standard, Todd et al. 2008). See below. |
| **DegDays** | The sum of the daily means, counting days below freezing as 0 |
| **MWAT** | Maximum Weekly Average Temperature: the warmest 7 consecutive days, averaging the daily **means** |
| **MWMT** | Maximum Weekly Maximum Temperature: the warmest 7 consecutive days, averaging the daily **maxima** |
| **M30AT** | Maximum 30-day Average Temperature: the warmest 30 consecutive days, averaging the daily **means** |

**DegDays**, where *D* is the set of days between the sliders:

```math
\text{DegDays} = \sum_{d \in D} \max\left(0,\ \bar{T}_d\right)
```

**MWAT, MWMT and M30AT** (`_rolling_max`) are found the same way. For each day *k*, average the daily value over days *k* to *k + L − 1*, then report the largest of those averages:

```math
\text{MWAT} = \max_k \frac{1}{7}\sum_{j=0}^{6} \bar{T}_{k+j}
\qquad
\text{MWMT} = \max_k \frac{1}{7}\sum_{j=0}^{6} T^{\max}_{k+j}
\qquad
\text{M30AT} = \max_k \frac{1}{30}\sum_{j=0}^{29} \bar{T}_{k+j}
```

A window counts only if **every day in it has data**. A gap of a day or more breaks the run, and windows across it are skipped. The summary shows the first and last date of the winning window.

**DailyMax** (2-hour running average). At each reading, WaTSS averages the readings from the preceding 2 hours: everything later than 2 hours before it, up to and including it. A window counts only once it spans at least 2 hours minus one reading interval, so a window at the very start, or straddling a logger gap, isn't used. DailyMax is the highest of these averages, and the summary shows the time of the reading that ends that window.

| Logger interval | Readings in each 2-hour window |
|---|---|
| 1 hour | 2 |
| 30 minutes | 4 |
| 15 minutes | 8 |

### English and Metric tabs

Everything is calculated in °C. The English tab converts each result to °F:

```math
T_{°F} = 1.8\,T_{°C} + 32
```

DegDays is a sum of temperature *differences* above freezing, so it's only multiplied by 1.8, not shifted by 32. English DegDays are °F-days above 32 °F.

## 4. Reference thresholds (`thresholds`)

These criteria from the WaTSS manual are shown next to the summary. They are stored in °C and converted for the English tab.

| Criterion | Value |
|---|---|
| Cold Tier 1 (CWQCC 2012), Jun–Sep | DailyMax 21.7 °C, MWAT 17 °C |
| Cold Tier 1, Oct–May | DailyMax 13 °C, MWAT 9 °C |
| Colorado River cutthroat trout survival (Roberts et al. 2013) | MWMT limit 26 °C |
| Recruitment (Coleman & Fausch 2007) | M30AT below 8 °C: no recruitment; above 9 °C: robust recruitment |
| Cutthroat growth | Best at 9–18 °C, peak near 15 °C |

## 5. Export

- **Export** (`export_text`) saves the green series between the sliders: two header lines, then `n,date time,temperature` with temperatures to 2 decimals. It can be loaded back into WaTSS. The file name records the filter, for example `PooseCreekDailyMaxRunning7.txt`.
- **Download R code** (`r_bundle`) saves a `.zip` holding a tidy CSV of both series and a ggplot2 script that redraws both plots. Plot lines break wherever the gap between readings is more than six reading intervals (`segments`).

## Worked example

**Try sample data** loads a synthetic hourly record (°F) from 2 June 2013 to 23 November 2014. With the sliders at the two ends, it has 12,948 readings over 540 days:

| Statistic | English | Metric | Period |
|---|---|---|---|
| AveTemp | 45.80 °F | 7.66 °C | |
| DailyMax | 71.80 °F | 22.11 °C | window ending 15 Jul 2014, 6:00 PM |
| DegDays | 7,455 | 4,142 | |
| MWAT | 63.04 °F | 17.24 °C | 9–15 Jul 2014 |
| MWMT | 70.25 °F | 21.25 °C | 9–15 Jul 2014 |
| M30AT | 60.99 °F | 16.11 °C | 4 Jul – 2 Aug 2014 |

You can reproduce these numbers without a browser:

```bash
cd WaTSS
python3 -c "
import watss
d = watss.parse(watss.sample_csv())
s = watss.compute_stats(d['t'], d['y'], 'F', d['dt'], d['t'][0], d['t'][-1])
print(s['n'], 'readings,', s['days'], 'days')
print(s['english'])
"
```

## References

- CWQCC (Colorado Water Quality Control Commission). 2012. *Regulation 31: The basic standards and methodologies for surface water*. Colorado Department of Public Health and the Environment, Denver.
- Coleman, M. A., and K. D. Fausch. 2007. Cold summer temperature limits recruitment of age-0 cutthroat trout in high-elevation Colorado streams. *Transactions of the American Fisheries Society* 136:1231–1244.
- Roberts, J. J., K. D. Fausch, D. P. Peterson, and M. B. Hooten. 2013. Fragmentation and thermal risks from climate change interact to affect persistence of native trout in the Colorado River basin. *Global Change Biology* 19:1383–1398.
- Rogers, K. B. 2015. *User manual for WaTSS 3.0 (Water temperature summary software)*. Colorado Parks and Wildlife, Fort Collins.
- Todd, A. S., M. A. Coleman, A. M. Konowal, M. K. May, S. Johnson, N. K. M. Vieira, and J. F. Saunders. 2008. Development of new water temperature criteria to protect Colorado's fisheries. *Fisheries* 33:433–443.
