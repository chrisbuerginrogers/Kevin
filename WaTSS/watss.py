"""WaTSS core: reading thermograph files, filtering, summary statistics, export.

Pure Python with no browser or UI code, so it can be tested with plain Python:

    python3 -c "import watss; print(watss.parse(watss.sample_csv())['dt'])"

Times are milliseconds since 1970-01-01, treating the logger's clock times as UTC
(no time-zone or daylight-saving shifts), so calendar days match the logger.
Temperatures stay in the file's own units except in compute_stats, which works in
degrees C and also reports English (degrees F) values.
"""

import bisect
import calendar
import csv
import math
import random
import re
import time

HOUR = 3_600_000
DAY = 86_400_000

# ---------------------------------------------------------------- reading files

_DATETIME = re.compile(
    r"^(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{1,4})[ T]+"
    r"(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?\s*([AaPp][Mm])?$"
)
_UNIT_SYMBOL = re.compile(r"(?:°|º|deg)\s*([CF])\b", re.I)
_UNIT_COLUMN = re.compile(r"Temp[^,\"]*,\s*[^A-Za-z0-9\s]{0,3}\s*([CF])\b", re.I)


def parse_datetime(text):
    """'9/1/11 7:50:54 PM', '06/02/13 13:00:00' or '2013-06-02 13:00' -> ms, else None.

    Dates are month/day/year unless the year comes first. Two-digit years below 70
    are 20xx. AM/PM is honoured when present, otherwise the clock is 24-hour.
    """
    m = _DATETIME.match(text.strip())
    if not m:
        return None
    a, b, c, hh, mi, ss, ampm = m.groups()
    if len(a) == 4:
        year, month, day = int(a), int(b), int(c)
    else:
        month, day, year = int(a), int(b), int(c)
        if len(c) <= 2:
            year += 2000 if year < 70 else 1900
    hour = int(hh)
    if ampm:
        hour = hour % 12 + (12 if ampm.lower() == "pm" else 0)
    if not (1 <= month <= 12 and 1 <= day <= 31 and hour <= 23 and int(mi) <= 59):
        return None
    return calendar.timegm((year, month, day, hour, int(mi), int(ss or 0))) * 1000


def detect_unit(text):
    """Return 'F' or 'C' if the first header lines name the unit (HOBOware does), else None."""
    head = " ".join(text.splitlines()[:5])
    m = _UNIT_SYMBOL.search(head) or _UNIT_COLUMN.search(head)
    return m.group(1).upper() if m else None


def _number(s):
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def parse(text):
    """Read a HOBOware .csv export or a WaTSS .txt export.

    Header lines are skipped automatically: the first row with a date/time followed by
    a number fixes which column holds the time stamp (the temperature is the next one).

    Returns {"t": [ms], "y": [temp], "ampm": bool, "dt": typical interval ms, "unit": "F"|"C"|None}.
    """
    text = text.lstrip("﻿")
    col = None
    ampm = False
    points = []
    for row in csv.reader(text.splitlines()):
        fields = [f.strip() for f in row]
        if not any(fields):
            continue
        if col is None:
            for i in range(len(fields) - 1):
                if parse_datetime(fields[i]) is not None and _number(fields[i + 1]) is not None:
                    col = i
                    break
            if col is None:
                continue
        if len(fields) <= col + 1:
            continue
        t = parse_datetime(fields[col])
        y = _number(fields[col + 1])
        if t is None or y is None:
            continue
        if fields[col][-2:].lower() in ("am", "pm"):
            ampm = True
        points.append((t, y))

    points.sort()
    t = [p[0] for p in points]
    y = [p[1] for p in points]
    return {"t": t, "y": y, "ampm": ampm, "dt": typical_interval(t), "unit": detect_unit(text)}


def typical_interval(t):
    """Median spacing between readings (ms), from the first 2,000 gaps."""
    gaps = sorted(b - a for a, b in zip(t[:2001], t[1:2001]) if b > a)
    return gaps[len(gaps) // 2] if gaps else HOUR


# ---------------------------------------------------------------- filters

def day_key(t):
    return t // DAY


def noon(day):
    return day * DAY + 12 * HOUR


def month_key(t):
    g = time.gmtime(t / 1000)
    return g.tm_year * 12 + g.tm_mon - 1


def mid_month(key):
    return calendar.timegm((key // 12, key % 12 + 1, 15, 12, 0, 0)) * 1000


def group(t, y, key, when, how="mean"):
    """Collapse consecutive readings that share key(t) into one point at when(key)."""
    out_t, out_y = [], []
    current, vals = None, []
    for ti, yi in zip(t, y):
        k = key(ti)
        if k != current:
            if vals:
                out_t.append(when(current))
                out_y.append(max(vals) if how == "max" else sum(vals) / len(vals))
            current, vals = k, []
        vals.append(yi)
    if vals:
        out_t.append(when(current))
        out_y.append(max(vals) if how == "max" else sum(vals) / len(vals))
    return out_t, out_y


def daily_max(t, y):
    """Highest reading on each calendar day, stamped at noon."""
    return group(t, y, day_key, noon, "max")


def daily_average(t, y):
    """Mean of all readings on each calendar day (0000-2400), stamped at noon."""
    return group(t, y, day_key, noon, "mean")


def weekly_average(t, y):
    """Mean of consecutive 7-day blocks starting on the first day of data,
    stamped at noon on the fourth day of each block."""
    if not t:
        return [], []
    d0 = day_key(t[0])
    return group(t, y, lambda ti: (day_key(ti) - d0) // 7, lambda k: noon(d0 + k * 7 + 3), "mean")


def monthly_average(t, y):
    """Mean of all readings in each calendar month, stamped at noon on the 15th."""
    return group(t, y, month_key, mid_month, "mean")


def running_average(t, y, window):
    """Centred running mean over `window` consecutive points."""
    n, w = len(y), max(1, int(window))
    if w > n:
        return [], []
    half = (w - 1) // 2
    sums = [0.0]
    for v in y:
        sums.append(sums[-1] + v)
    starts = range(n - w + 1)
    return [t[s + half] for s in starts], [(sums[s + w] - sums[s]) / w for s in starts]


def filter_series(t, y, filt="raw", averaging="none", window=24):
    """The two WaTSS dropdowns: Filter ('raw' | 'max') then Averaging
    ('none' | 'daily' | 'weekly' | 'monthly' | 'running' with `window` points)."""
    t, y = list(t), list(y)
    if filt == "max":
        t, y = daily_max(t, y)
    if averaging == "daily":
        t, y = daily_average(t, y)
    elif averaging == "weekly":
        t, y = weekly_average(t, y)
    elif averaging == "monthly":
        t, y = monthly_average(t, y)
    elif averaging == "running":
        t, y = running_average(t, y, window)
    return t, y


# ---------------------------------------------------------------- statistics

def to_celsius(v, unit):
    return (v - 32) / 1.8 if unit == "F" else v


def to_fahrenheit(c):
    return c * 1.8 + 32


def _rolling_max(days, length, field):
    """Warmest run of `length` consecutive calendar days, averaging `field` of each day.
    Returns (value, first_day, last_day) or None if there is no complete run."""
    best = None
    for k in sorted(days):
        run = [days.get(k + q) for q in range(length)]
        if None in run:
            continue
        v = sum(d[field] for d in run) / length
        if best is None or v > best[0]:
            best = (v, k, k + length - 1)
    return best


def compute_stats(t, y, unit, dt, t_left, t_right):
    """Summary statistics for the raw readings between the sliders (inclusive).

    AveTemp  mean of the raw readings
    DailyMax highest 2-hour running average (Colorado standard, Todd et al. 2008)
    DegDays  sum over calendar days of the daily mean above freezing
    MWAT     warmest 7-day mean of daily mean temperatures
    MWMT     warmest 7-day mean of daily maximum temperatures
    M30AT    warmest 30-day mean of daily mean temperatures

    Returns None if no readings fall between the sliders, otherwise
    {"n", "days", "metric": {...}, "english": {...}}; times are ms, missing values None.
    """
    a = bisect.bisect_left(t, t_left)
    b = bisect.bisect_right(t, t_right)
    if b <= a:
        return None
    tt = t[a:b]
    c = [to_celsius(v, unit) for v in y[a:b]]

    ave = sum(c) / len(c)

    # DailyMax: trailing 2-hour windows, counted only once a window spans ~2 h of readings.
    span, need = 2 * HOUR, max(0, 2 * HOUR - dt) - 1000
    j, total, dmax = 0, 0.0, None
    for i, v in enumerate(c):
        total += v
        while tt[j] <= tt[i] - span:
            total -= c[j]
            j += 1
        if tt[i] - tt[j] >= need:
            m = total / (i - j + 1)
            if dmax is None or m > dmax[0]:
                dmax = (m, tt[i])

    days = {}
    for ti, v in zip(tt, c):
        d = days.setdefault(day_key(ti), {"sum": 0.0, "n": 0, "max": -math.inf})
        d["sum"] += v
        d["n"] += 1
        d["max"] = max(d["max"], v)
    for d in days.values():
        d["mean"] = d["sum"] / d["n"]

    degdays = sum(max(0.0, d["mean"]) for d in days.values())
    mwat = _rolling_max(days, 7, "mean")
    mwmt = _rolling_max(days, 7, "max")
    m30at = _rolling_max(days, 30, "mean")

    def pack(conv, dd_scale):
        def roll(r, name):
            return {
                name: conv(r[0]) if r else None,
                name + "From": r[1] * DAY if r else None,
                name + "To": r[2] * DAY if r else None,
            }
        out = {
            "ave": conv(ave),
            "dmax": conv(dmax[0]) if dmax else None,
            "dmaxAt": dmax[1] if dmax else None,
            "degdays": degdays * dd_scale,
        }
        out.update(roll(mwat, "mwat"))
        out.update(roll(mwmt, "mwmt"))
        out.update(roll(m30at, "m30at"))
        return out

    return {
        "n": len(c),
        "days": len(days),
        "metric": pack(lambda v: v, 1.0),
        "english": pack(to_fahrenheit, 1.8),
    }


THRESHOLDS_C = [
    ("Cold Tier 1 (CWQCC 2012), Jun–Sep", "DailyMax {21.7}, MWAT {17}"),
    ("Cold Tier 1, Oct–May", "DailyMax {13}, MWAT {9}"),
    ("MWMT {26}", "limit for Colorado River cutthroat trout survival (Roberts et al. 2013)"),
    ("M30AT below {8}", "no recruitment; above {9} for robust recruitment (Coleman & Fausch 2007)"),
    ("Cutthroat growth", "best at {9}–{18}, peak near {15}"),
]


def thresholds(system="metric"):
    """Reference criteria from the WaTSS manual as [(title, detail)] in the chosen units."""
    unit = "°F" if system == "english" else "°C"

    def fill(s):
        def repl(m):
            v = float(m.group(1))
            if system == "english":
                v = to_fahrenheit(v)
            return f"{v:.1f}".rstrip("0").rstrip(".") + " " + unit
        return re.sub(r"\{([\d.]+)\}", repl, s)

    return [(fill(title), fill(detail)) for title, detail in THRESHOLDS_C]


# ---------------------------------------------------------------- export

def format_timestamp(t):
    """ms -> '9/1/11 7:50:54 PM' (the HOBOware / WaTSS style)."""
    g = time.gmtime(t / 1000)
    hour = g.tm_hour % 12 or 12
    ampm = "PM" if g.tm_hour >= 12 else "AM"
    return f"{g.tm_mon}/{g.tm_mday}/{g.tm_year % 100:02d} {hour}:{g.tm_min:02d}:{g.tm_sec:02d} {ampm}"


def export_text(source_name, t, y, t_left, t_right):
    """WaTSS export: two header lines, then 'n,date time,temp' for points between the
    sliders. The result can be read back in with parse()."""
    a = bisect.bisect_left(t, t_left)
    b = bisect.bisect_right(t, t_right)
    lines = ["This file is a subset of file:", source_name]
    for n, i in enumerate(range(a, b), 1):
        lines.append(f"{n},{format_timestamp(t[i])},{y[i]:.2f}")
    return "\r\n".join(lines) + "\r\n"


def export_name(source_name, filt, averaging, window):
    """Suggested file name, e.g. 'PooseCreekDailyMaxRunning7.txt'."""
    base = re.sub(r"\.[^.]+$", "", source_name)
    tag = {"daily": "DailyAve", "weekly": "WeeklyAve", "monthly": "MonthlyAve",
           "running": f"Running{int(window)}"}.get(averaging, "")
    return f"{base}{'DailyMax' if filt == 'max' else ''}{tag}.txt"


# ---------------------------------------------------------------- sample data

def sample_csv(seed=7):
    """Synthetic hourly stream temperatures (°F), Jun 2013 – Nov 2014, in HOBOware
    export format: a seasonal cycle, a daily cycle that grows in summer, weather-like
    drift, and readings held near freezing under winter ice. Demo data only."""
    rng = random.Random(seed)
    lines = ['"Plot Title: Sample Creek (synthetic demo data)"',
             '"#","Date Time, GMT-07:00","Temp, °F"']
    t = calendar.timegm((2013, 6, 2, 12, 0, 0)) * 1000
    end = calendar.timegm((2014, 11, 23, 23, 0, 0)) * 1000
    drift, n = 0.0, 0
    while t <= end:
        g = time.gmtime(t / 1000)
        seasonal = 40 + 21 * math.cos(2 * math.pi * (g.tm_yday - 1 - 205) / 365)
        drift = 0.985 * drift + rng.gauss(0, 0.35)
        diel = max(0.0, seasonal - 36) * 0.28 * math.sin(2 * math.pi * (g.tm_hour - 10) / 24)
        v = max(32.2 + rng.random() * 0.3, seasonal + diel + drift + rng.gauss(0, 0.3))
        n += 1
        lines.append(f"{n},{format_timestamp(t)},{v:.3f}")
        t += HOUR
    return "\r\n".join(lines) + "\r\n"
