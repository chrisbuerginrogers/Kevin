"""JakeOmatic core: fish survey calculations with no UI code.

Lake surveys (CPUE, PSD/RSD, relative weight) and stream surveys (two-pass removal
population estimates and densities), plus Level II summary tables, Chapman-Petersen
mark-recapture, survey save/load and CSV export.

Pure Python, so it can be tested without a browser:

    python3 -c "import jakeomatic as j; m, r = j.sample_survey('stream'); print(j.stream_stats(r, j.default_lut(), 'LOC', 600, 20, 150, 600))"

Conventions
-----------
* A record is one row of the fish table: {"species", "count", "length_mm", "weight_g",
  "status", "mark", "tag_id", "pass_num"}. "count" is the number of fish the row
  stands for (normally 1), and every total, CPUE, percentage and length frequency
  is weighted by it.
* A length or weight of 0 means "not measured"; such fish count toward totals but
  not toward length or weight summaries.
* Functions return plain numbers, or None when a value can't be calculated.
"""

import csv
import io
import json
import math
import random

# ---------------------------------------------------------------- constants

MM_PER_IN = 25.4
G_PER_LB = 453.59237
M2_PER_FT2 = 0.09290304
KM_PER_FT = 0.0003048
MI_PER_KM = 0.621371192
AC_PER_HA = 2.4710538
Z95 = 1.96

# Standard weight (log10 Ws = slope * log10 L(mm) + intercept, Ws in g) and
# length categories (mm). Sources: Bister et al. 2000 (NAJM 20:570-574),
# Hyatt & Hubert 2001 (NAJM 21:253-254), Muoneke & Pope 1999 (NAJM 19:878-879).
DEFAULT_LUT = [
    # name,                    code,  slope,  intercept, stock, quality, preferred, memorable, trophy
    ("BROWN TROUT",            "LOC", 2.96,   -4.867, 150, 230, 300, 380, 460),
    ("RAINBOW TROUT",          "RBT", 2.99,   -4.898, 250, 400, 500, 650, 800),
    ("CUTTHROAT TROUT - SRN",  "SRN", 3.086,  -5.192, 200, 350, 450, 600, 750),
    ("CUTTHROAT TROUT - CRN",  "CRN", 3.086,  -5.192, 200, 350, 450, 600, 750),
    ("CUTTHROAT TROUT - GBN",  "GBN", 3.086,  -5.192, 200, 350, 450, 600, 750),
    ("CUTTHROAT TROUT - RGN",  "RGN", 3.086,  -5.192, 200, 350, 450, 600, 750),
    ("BROOK TROUT",            "BRK", 3.103,  -5.186, 200, 330, 0, 0, 0),
    ("MOUNTAIN WHITEFISH",     "MWF", 3.036,  -5.086, 0, 0, 0, 0, 0),
    ("ARCTIC GRAYLING",        "GRA", 0, 0, 0, 0, 0, 0, 0),
    ("SPLAKE",                 "SPL", 0, 0, 0, 0, 0, 0, 0),
    ("LAKE TROUT",             "MAC", 3.264,  -5.681, 300, 500, 650, 800, 1000),
    ("KOKANEE",                "KOK", 0, 0, 0, 0, 0, 0, 0),
    ("ARCTIC CHAR",            "ARC", 0, 0, 0, 0, 0, 0, 0),
    ("BLUEHEAD SUCKER",        "BHS", 0, 0, 0, 0, 0, 0, 0),
    ("FLANNELMOUTH SUCKER",    "FMS", 0, 0, 0, 0, 0, 0, 0),
    ("LONGNOSE SUCKER",        "LGS", 0, 0, 0, 0, 0, 0, 0),
    ("MOUNTAIN SUCKER",        "MOS", 0, 0, 0, 0, 0, 0, 0),
    ("RAZORBACK SUCKER",       "RBS", 0, 0, 0, 0, 0, 0, 0),
    ("RIO GRANDE SUCKER",      "RGS", 0, 0, 0, 0, 0, 0, 0),
    ("RIVER CARPSUCKER",       "RCS", 2.992,  -4.839, 180, 280, 360, 460, 560),
    ("WHITE SUCKER",           "WHS", 2.94,   -4.755, 150, 250, 330, 410, 510),
]
LUT_FIELDS = ("name", "code", "slope", "intercept", "stock", "quality", "preferred", "memorable", "trophy")

SALMONID_CODES = {"LOC", "RBT", "SRN", "CRN", "GBN", "RGN", "BRK", "MWF", "GRA", "SPL", "MAC", "KOK", "ARC"}
SUCKER_CODES = {"BHS", "FMS", "LGS", "MOS", "RBS", "RGS", "RCS", "WHS"}

# ---------------------------------------------------------------- small helpers


def _num(value, default=0.0):
    """Float from user input; blanks and junk become `default`."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _int(value, default=0):
    return int(round(_num(value, default)))


def _wmean(pairs):
    """Weighted mean of (value, weight) pairs, or None."""
    tot = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / tot if tot else None


def _per(value, divisor):
    return value / divisor if value is not None and divisor else None


# ---------------------------------------------------------------- species LUT


def default_lut():
    return [dict(zip(LUT_FIELDS, row)) for row in DEFAULT_LUT]


def clean_lut(rows):
    """Validate an edited LUT: codes upper-cased, numbers coerced, rows without a code dropped,
    duplicate codes keep their first row."""
    out, seen = [], set()
    for r in rows or []:
        code = str(r.get("code", "")).strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append({
            "name": str(r.get("name", "")).strip().upper() or code,
            "code": code,
            "slope": _num(r.get("slope")),
            "intercept": _num(r.get("intercept")),
            **{k: _int(r.get(k)) for k in ("stock", "quality", "preferred", "memorable", "trophy")},
        })
    return out


def lookup(lut, code):
    code = (code or "").upper()
    return next((s for s in lut if s["code"] == code), None)


def species_options(lut, group="all"):
    """Species for the picker: 'all', 'salmonid' or 'sucker'."""
    keep = {"salmonid": SALMONID_CODES, "sucker": SUCKER_CODES}.get(group)
    return [{"code": s["code"], "name": s["name"]} for s in lut if keep is None or s["code"] in keep]


# ---------------------------------------------------------------- records


def make_record(fields, unit="mm"):
    """Build a record from form input. Length is entered in `unit` ('mm' or 'cm') and stored in mm.
    Returns (record, None) or (None, error message)."""
    species = str(fields.get("species", "")).strip().upper()
    if not species:
        return None, "Choose a species"
    length = _num(fields.get("length"))
    weight = _num(fields.get("weight"))
    count = _int(fields.get("count"), 1)
    if length < 0 or weight < 0:
        return None, "Length and weight can't be negative"
    if count < 1:
        return None, "Count must be at least 1"
    return {
        "species": species,
        "count": count,
        "length_mm": round(length * 10 if unit == "cm" else length, 3),
        "weight_g": weight,
        "status": str(fields.get("status", "")).strip(),
        "mark": str(fields.get("mark", "")).strip(),
        "tag_id": str(fields.get("tag_id", "")).strip(),
        "pass_num": 2 if _int(fields.get("pass_num"), 1) == 2 else 1,
    }, None


def normalize_record(r):
    """Coerce a record read from a saved survey (old or new) into the standard shape."""
    return {
        "species": str(r.get("species", "")).strip().upper(),
        "count": max(1, _int(r.get("count"), 1)),
        "length_mm": max(0.0, _num(r.get("length_mm"))),
        "weight_g": max(0.0, _num(r.get("weight_g"))),
        "status": str(r.get("status") or ""),
        "mark": str(r.get("mark") or ""),
        "tag_id": str(r.get("tag_id") or ""),
        "pass_num": 2 if _int(r.get("pass_num"), 1) == 2 else 1,
    }


def select(records, code=None, min_mm=None, max_mm=None):
    """Records of one species (None = all), optionally within a length range (inclusive)."""
    out = []
    for r in records:
        if code and r["species"] != code:
            continue
        if min_mm is not None and r["length_mm"] < min_mm:
            continue
        if max_mm is not None and r["length_mm"] > max_mm:
            continue
        out.append(r)
    return out


def fish(rows):
    """Number of fish the rows stand for."""
    return sum(r["count"] for r in rows)


def species_in_order(records):
    seen = []
    for r in records:
        if r["species"] not in seen:
            seen.append(r["species"])
    return seen


# ---------------------------------------------------------------- weights


def standard_weight(length_mm, sp):
    """Ws (g) from the species' standard-weight equation, or None."""
    if not sp or not sp["slope"] or length_mm <= 0:
        return None
    return 10 ** (sp["slope"] * math.log10(length_mm) + sp["intercept"])


def relative_weight(length_mm, weight_g, sp):
    """Wr = 100 * W / Ws, or None."""
    ws = standard_weight(length_mm, sp)
    return 100 * weight_g / ws if ws and weight_g > 0 else None


def estimate_weights(records, lut):
    """Fill missing weights (0) with the standard weight for the fish's length (i.e. Wr = 100).
    Returns (new records, number filled)."""
    out, n = [], 0
    for r in records:
        r = dict(r)
        if r["weight_g"] <= 0 and r["length_mm"] > 0:
            ws = standard_weight(r["length_mm"], lookup(lut, r["species"]))
            if ws:
                r["weight_g"] = round(ws, 1)
                n += 1
        out.append(r)
    return out, n


def mean_wr(rows, sp):
    return _wmean([(wr, r["count"]) for r in rows
                   if (wr := relative_weight(r["length_mm"], r["weight_g"], sp)) is not None])


def length_summary(rows):
    """Weighted mean, min and max length (mm) of measured fish."""
    measured = [r for r in rows if r["length_mm"] > 0]
    if not measured:
        return None, None, None
    return (_wmean([(r["length_mm"], r["count"]) for r in measured]),
            min(r["length_mm"] for r in measured), max(r["length_mm"] for r in measured))


def weight_summary(rows):
    """Weighted mean, min and max weight (g) of weighed fish."""
    weighed = [r for r in rows if r["weight_g"] > 0]
    if not weighed:
        return None, None, None
    return (_wmean([(r["weight_g"], r["count"]) for r in weighed]),
            min(r["weight_g"] for r in weighed), max(r["weight_g"] for r in weighed))


# ---------------------------------------------------------------- size structure


def size_structure(rows, sp):
    """PSD and RSD-P (percent). PSD = 100 * (fish >= quality) / (fish >= stock);
    RSD-P = 100 * (fish >= preferred) / (fish >= stock). None if the LUT lacks the lengths."""
    if not sp or sp["stock"] <= 0:
        return {"stock": None, "psd": None, "rsdp": None}
    n_stock = fish([r for r in rows if r["length_mm"] >= sp["stock"]])

    def pct(cut):
        if not cut or not n_stock:
            return None
        return 100 * fish([r for r in rows if r["length_mm"] >= cut]) / n_stock

    return {"stock": n_stock, "psd": pct(sp["quality"]), "rsdp": pct(sp["preferred"])}


# ---------------------------------------------------------------- lake survey


def lake_stats(records, lut, code, e_hours, g_hours, t_hours):
    """Statistics for one species in a lake survey. CPUE = fish per hour of electrofishing (E),
    gill net (G) and trap net (T) effort; '>=S' uses only stock-length fish."""
    sp = lookup(lut, code)
    rows = select(records, code)
    n = fish(rows)
    ss = size_structure(rows, sp)
    hours = {"e": _num(e_hours), "g": _num(g_hours), "t": _num(t_hours)}
    mean_len, _, _ = length_summary(rows)
    mean_wt, _, _ = weight_summary(rows)
    return {
        "n": n,
        "cpue": {k: _per(n, h) for k, h in hours.items()},
        "cpueStock": {k: _per(ss["stock"], h) for k, h in hours.items()},
        "psd": ss["psd"],
        "rsdp": ss["rsdp"],
        "meanLenIn": mean_len / MM_PER_IN if mean_len else None,
        "meanWtLb": mean_wt / G_PER_LB if mean_wt else None,
        "meanWr": mean_wr(rows, sp),
    }


# ---------------------------------------------------------------- population estimates


def two_pass_removal(c1, c2):
    """Seber & Le Cren (1967) two-pass removal estimate.
    N = c1^2 / (c1 - c2), p = (c1 - c2) / c1, Var(N) = c1^2 c2^2 (c1 + c2) / (c1 - c2)^4.
    Not possible when the second pass catches as many fish as the first."""
    if c1 <= 0 or c2 >= c1:
        reason = "no fish on the 1st pass" if c1 <= 0 else "2nd pass caught as many as the 1st"
        return {"valid": False, "reason": reason, "N": None, "p": None, "se": None, "ci": None,
                "lcl": None, "ucl": None}
    n = c1 * c1 / (c1 - c2)
    var = c1 ** 2 * c2 ** 2 * (c1 + c2) / (c1 - c2) ** 4
    se = math.sqrt(var)
    ci = Z95 * se
    return {"valid": True, "reason": "", "N": n, "p": (c1 - c2) / c1, "se": se, "ci": ci,
            "lcl": max(c1 + c2, n - ci), "ucl": n + ci}


def chapman_petersen(m, c, r):
    """Chapman's modified Petersen mark-recapture estimate with Seber's (1970) variance.
    m = marked on the first visit, c = captured on the second, r = recaptures among c.
    Also returns the unmodified Petersen estimate (m*c/r; the t=2 ML estimator of Otis et al. 1978)."""
    m, c, r = _int(m), _int(c), _int(r)
    if m <= 0 or c <= 0 or r < 0 or r > min(m, c):
        return {"valid": False, "reason": "need M > 0, C > 0 and 0 <= R <= min(M, C)"}
    n = (m + 1) * (c + 1) / (r + 1) - 1
    var = (m + 1) * (c + 1) * (m - r) * (c - r) / ((r + 1) ** 2 * (r + 2))
    ci = Z95 * math.sqrt(var)
    return {"valid": True, "reason": "", "N": n, "petersen": m * c / r if r else None,
            "p": r / c, "variance": var, "ci": ci, "lcl": max(m + c - r, n - ci), "ucl": n + ci}


# ---------------------------------------------------------------- stream survey


def station(length_ft, width_ft):
    """Station area (ha) and length (km) from feet."""
    length_ft, width_ft = _num(length_ft), _num(width_ft)
    area_ha = length_ft * width_ft * M2_PER_FT2 / 10_000 if length_ft > 0 and width_ft > 0 else 0
    return area_ha, length_ft * KM_PER_FT if length_ft > 0 else 0


def _cut(min_cut, max_cut):
    lo = _num(min_cut)
    hi = _num(max_cut)
    return lo, (hi if hi > 0 else None)


def _stream_species(rows, sp, area_ha, length_km):
    """Removal estimate, densities and biomass for one species' rows (already size-filtered)."""
    c1 = fish([r for r in rows if r["pass_num"] == 1])
    c2 = fish([r for r in rows if r["pass_num"] == 2])
    est = two_pass_removal(c1, c2)
    mean_wt, _, _ = weight_summary(rows)
    big_n, ci = est["N"], est["ci"]
    kg = big_n * mean_wt / 1000 if big_n is not None and mean_wt else None
    kg_ci = ci * mean_wt / 1000 if ci is not None and mean_wt else None
    return {
        "n": fish(rows), "pass1": c1, "pass2": c2, "removal": est, "meanWtG": mean_wt,
        "meanWr": mean_wr(rows, sp),
        "perHa": _per(big_n, area_ha), "perHaCi": _per(ci, area_ha),
        "kgHa": _per(kg, area_ha), "kgHaCi": _per(kg_ci, area_ha),
        "perKm": _per(big_n, length_km), "perKmCi": _per(ci, length_km),
        "kgKm": _per(kg, length_km), "kgKmCi": _per(kg_ci, length_km),
    }


def stream_stats(records, lut, code, length_ft, width_ft, min_cut, max_cut):
    """Statistics for one species in a two-pass stream survey, using only fish whose length is
    within [min_cut, max_cut] mm (max 0 = no upper limit). Densities use the removal estimate."""
    area_ha, length_km = station(length_ft, width_ft)
    lo, hi = _cut(min_cut, max_cut)
    out = _stream_species(select(records, code, lo, hi), lookup(lut, code), area_ha, length_km)
    out.update(areaHa=area_ha, lengthKm=length_km)
    return out


# ---------------------------------------------------------------- charts


def length_frequency(records, code, bin_mm=50, min_mm=None, max_mm=None):
    """Counts of measured fish in bins of `bin_mm`, from 0 to the largest fish.
    Returns {"edges": [bin lower edges in mm], "counts": [...]}."""
    rows = [r for r in select(records, code, min_mm, max_mm) if r["length_mm"] > 0]
    if not rows:
        return {"edges": [], "counts": []}
    nbins = int(max(r["length_mm"] for r in rows) // bin_mm) + 1
    counts = [0] * nbins
    for r in rows:
        counts[int(r["length_mm"] // bin_mm)] += r["count"]
    return {"edges": [i * bin_mm for i in range(nbins)], "counts": counts}


def wr_points(records, lut, code, min_mm=None, max_mm=None):
    """[{x: length_mm, y: Wr}] for fish of one species with length, weight and a Ws equation."""
    sp = lookup(lut, code)
    pts = []
    for r in select(records, code, min_mm, max_mm):
        wr = relative_weight(r["length_mm"], r["weight_g"], sp)
        if wr is not None:
            pts.append({"x": r["length_mm"], "y": wr})
    return pts


# ---------------------------------------------------------------- Level II tables


def _fmt(v, nd=1, pm=False):
    if v is None:
        return "—"
    return ("±" if pm else "") + f"{v:,.{nd}f}"


def _lf_table(records, codes, bin_cm, top_cm):
    edges = list(range(0, top_cm, bin_cm))
    headers = ["Species"] + [f"{b}-{b + bin_cm}" for b in edges] + [f">{top_cm}"]
    rows = []
    for code in codes:
        measured = [r for r in records if r["species"] == code and r["length_mm"] > 0]
        cells = [fish([r for r in measured if b * 10 <= r["length_mm"] < (b + bin_cm) * 10]) for b in edges]
        cells.append(fish([r for r in measured if r["length_mm"] >= top_cm * 10]))
        rows.append([code] + [str(c) if c else "" for c in cells])
    return {"title": "Length frequency (cm)", "headers": headers, "rows": rows}


def level2_lake(records, lut, e_hours, g_hours, t_hours):
    """Level II tables for a lake survey: per-species summary and 3 cm length frequency."""
    codes = species_in_order(records)
    total = fish(records)
    headers = ["Species", "# Caught", "% Catch", "Mean Ln (in)", "Ln Range (in)", "Mean Wt (lb)",
               "Wt Range (lb)", "E CPUE", "G CPUE", "T CPUE", "PSD", "RSD-P", "Mean Wr"]
    rows = []
    for code in codes:
        sp = lookup(lut, code)
        sel = select(records, code)
        st = lake_stats(records, lut, code, e_hours, g_hours, t_hours)
        _, lmin, lmax = length_summary(sel)
        _, wmin, wmax = weight_summary(sel)
        rows.append([
            code, str(st["n"]), _fmt(100 * st["n"] / total if total else None) + "%",
            _fmt(st["meanLenIn"], 2),
            f"{lmin / MM_PER_IN:.1f}–{lmax / MM_PER_IN:.1f}" if lmin else "—",
            _fmt(st["meanWtLb"], 3),
            f"{wmin / G_PER_LB:.3f}–{wmax / G_PER_LB:.3f}" if wmin else "—",
            _fmt(st["cpue"]["e"], 2), _fmt(st["cpue"]["g"], 2), _fmt(st["cpue"]["t"], 2),
            _fmt(st["psd"]), _fmt(st["rsdp"]), _fmt(mean_wr(sel, sp)),
        ])
    return [{"title": "Summary information", "headers": headers, "rows": rows},
            _lf_table(records, codes, 3, 96)]


def level2_stream(records, lut, length_ft, width_ft, min_cut, max_cut):
    """Level II tables for a two-pass stream survey (fish within the size cut only):
    per-species removal estimates and densities in English units, and 2 cm length frequency."""
    area_ha, length_km = station(length_ft, width_ft)
    area_ac, length_mi = area_ha * AC_PER_HA, length_km * MI_PER_KM
    lo, hi = _cut(min_cut, max_cut)
    kept = select(records, None, lo, hi)
    codes = species_in_order(kept)
    total = fish(kept)
    headers = ["Species", "# Caught", "% Catch", "1st Pass", "2nd Pass", "Capture P", "Pop Est",
               "95% CI", "#/Mile", "95% CI", "#/Acre", "95% CI", "Lb/Acre", "95% CI", "Mean Wr"]
    rows = []
    for code in codes:
        s = _stream_species(select(kept, code), lookup(lut, code), area_ha, length_km)
        est = s["removal"]
        lb = est["N"] * s["meanWtG"] / G_PER_LB if est["N"] is not None and s["meanWtG"] else None
        lb_ci = est["ci"] * s["meanWtG"] / G_PER_LB if est["ci"] is not None and s["meanWtG"] else None
        rows.append([
            code, str(s["n"]), _fmt(100 * s["n"] / total if total else None) + "%",
            str(s["pass1"]), str(s["pass2"]), _fmt(est["p"], 3),
            _fmt(est["N"], 0), _fmt(est["ci"], 0, True),
            _fmt(_per(est["N"], length_mi)), _fmt(_per(est["ci"], length_mi), 1, True),
            _fmt(_per(est["N"], area_ac)), _fmt(_per(est["ci"], area_ac), 1, True),
            _fmt(_per(lb, area_ac), 2), _fmt(_per(lb_ci, area_ac), 2, True),
            _fmt(s["meanWr"]),
        ])
    cut = f"{lo:g}–{hi:g} mm" if hi else f"≥ {lo:g} mm"
    return [{"title": f"Summary information (fish {cut})", "headers": headers, "rows": rows},
            _lf_table(kept, codes, 2, 60)]


# ---------------------------------------------------------------- export, save, load


def _csv(rows):
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


def tables_csv(tables):
    """Level II tables as one CSV, each preceded by its title."""
    rows = []
    for t in tables:
        rows += [[t["title"]], t["headers"], *t["rows"], []]
    return _csv(rows)


def records_csv(records, lut, kind="lf"):
    """'lf': every record; 'wr': length, weight, standard weight and Wr."""
    if kind == "lf":
        rows = [["Species", "Pass", "Count", "Length_mm", "Weight_g", "Status", "Mark", "Tag_ID"]]
        rows += [[r["species"], r["pass_num"], r["count"], f"{r['length_mm']:g}", f"{r['weight_g']:g}",
                  r["status"], r["mark"], r["tag_id"]] for r in records]
    else:
        rows = [["Species", "Count", "Length_mm", "Weight_g", "Ws_g", "Wr"]]
        for r in records:
            sp = lookup(lut, r["species"])
            ws = standard_weight(r["length_mm"], sp)
            wr = relative_weight(r["length_mm"], r["weight_g"], sp)
            rows.append([r["species"], r["count"], f"{r['length_mm']:g}", f"{r['weight_g']:g}",
                         f"{ws:.1f}" if ws else "", f"{wr:.2f}" if wr is not None else ""])
    return _csv(rows)


LAKE_META = ("water", "date", "gear", "drainage", "crew", "water_code", "utm_zone", "utm_x", "utm_y",
             "e_hours", "g_hours", "t_hours", "notes")
STREAM_META = ("water", "date", "location", "drainage", "crew", "water_code", "utm_zone", "utm_x",
               "utm_y", "station_length", "station_width", "min_cut", "max_cut", "notes")


def survey_json(mode, meta, records):
    """Saved survey file (same layout as JakeOmatic 3.0, so either version can read it)."""
    keys = LAKE_META if mode == "lake" else STREAM_META
    data = {"type": mode, **{k: meta.get(k, "") for k in keys}, "records": records}
    return json.dumps(data, indent=2)


def read_survey(text):
    """Parse a saved survey. Returns (mode, meta, records); raises ValueError if it isn't one."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"not a JSON file ({e.msg})") from None
    if not isinstance(data, dict) or not isinstance(data.get("records", []), list):
        raise ValueError("not a JakeOmatic survey")
    mode = "stream" if data.get("type") == "stream" else "lake"
    keys = LAKE_META if mode == "lake" else STREAM_META
    meta = {k: "" if data.get(k) is None else str(data[k]) for k in keys if k in data}
    return mode, meta, [normalize_record(r) for r in data.get("records", []) if isinstance(r, dict)]


def file_stem(meta, mode):
    water = "_".join(str(meta.get("water") or mode).split())
    return "".join(ch for ch in water if ch.isalnum() or ch in "_-") or mode


# ---------------------------------------------------------------- demo data


def sample_survey(mode, seed=3):
    """Made-up survey for trying the program. Returns (meta, records)."""
    rng = random.Random(seed)
    lut = default_lut()

    def fishrow(code, length, pass_num=1, weigh=True):
        ws = standard_weight(length, lookup(lut, code))
        w = round(ws * rng.uniform(0.82, 1.12), 1) if ws and weigh else 0.0
        return {"species": code, "count": 1, "length_mm": float(round(length)), "weight_g": w,
                "status": "", "mark": "", "tag_id": "", "pass_num": pass_num}

    if mode == "lake":
        meta = {"water": "Demo Reservoir", "date": "2025-06-18", "gear": "Gill net", "crew": "Demo",
                "water_code": "99999", "e_hours": "0", "g_hours": "24", "t_hours": "0",
                "notes": "Synthetic demo data"}
        recs = [fishrow("RBT", rng.gauss(330, 70)) for _ in range(38)]
        recs += [fishrow("LOC", rng.gauss(300, 90)) for _ in range(17)]
        recs += [fishrow("WHS", rng.gauss(340, 60)) for _ in range(24)]
        recs += [fishrow("MAC", rng.gauss(520, 120)) for _ in range(5)]
    else:
        meta = {"water": "Demo Creek", "date": "2025-08-12", "location": "Station 1", "crew": "Demo",
                "water_code": "99998", "station_length": "600", "station_width": "18",
                "min_cut": "150", "max_cut": "600", "notes": "Synthetic demo data"}
        recs = []
        for code, n, mu, sd, p in (("LOC", 160, 230, 70, 0.62), ("BRK", 70, 170, 40, 0.55),
                                   ("MOS", 30, 130, 25, 0.5)):
            remaining = n
            for pass_num in (1, 2):
                caught = sum(rng.random() < p for _ in range(remaining))
                remaining -= caught
                recs += [fishrow(code, max(40, rng.gauss(mu, sd)), pass_num, weigh=rng.random() < 0.9)
                         for _ in range(caught)]
    return meta, [r for r in recs if r["length_mm"] > 0]
