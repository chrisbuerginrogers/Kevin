"""PyScript bridge between the JakeOmatic page (JavaScript UI) and jakeomatic.py.

Holds the fish records for each survey and the species LUT in Python, and exposes
window.Jake for the page to call. All calculations live in jakeomatic.py.
"""

import js
from pyodide.ffi import create_proxy, to_js
from pyscript import window

import jakeomatic as jk

state = {"lut": jk.default_lut(), "records": {"lake": [], "stream": []}}


def _js(obj):
    return to_js(obj, dict_converter=js.Object.fromEntries)


def _py(obj):
    return obj.to_py() if hasattr(obj, "to_py") else obj


def _recs(mode):
    return state["records"][mode]


# ---- species LUT
def lut_get():
    return _js(state["lut"])


def lut_set(rows):
    state["lut"] = jk.clean_lut(_py(rows)) or jk.default_lut()
    return _js(state["lut"])


def lut_reset():
    state["lut"] = jk.default_lut()
    return _js(state["lut"])


def species(group):
    return _js(jk.species_options(state["lut"], group))


# ---- records
def records(mode):
    return _js(_recs(mode))


def add(mode, fields, unit):
    rec, err = jk.make_record(_py(fields), unit)
    if err:
        return _js({"ok": False, "error": err})
    _recs(mode).append(rec)
    return _js({"ok": True, "record": rec})


def update(mode, index, fields, unit):
    rec, err = jk.make_record(_py(fields), unit)
    if err:
        return _js({"ok": False, "error": err})
    _recs(mode)[int(index)] = rec
    return _js({"ok": True, "record": rec})


def delete(mode, index):
    del _recs(mode)[int(index)]


def estimate_weights(mode):
    state["records"][mode], n = jk.estimate_weights(_recs(mode), state["lut"])
    return n


# ---- statistics and charts
def lake_stats(code, e, g, t):
    return _js(jk.lake_stats(_recs("lake"), state["lut"], code, e, g, t))


def stream_stats(code, length_ft, width_ft, min_cut, max_cut):
    return _js(jk.stream_stats(_recs("stream"), state["lut"], code, length_ft, width_ft, min_cut, max_cut))


def charts(mode, code, bin_mm, min_cut, max_cut):
    lo, hi = jk._cut(min_cut, max_cut) if mode == "stream" else (None, None)
    return _js({"lf": jk.length_frequency(_recs(mode), code, bin_mm, lo, hi),
                "wr": jk.wr_points(_recs(mode), state["lut"], code, lo, hi)})


def level2(mode, a, b, c, d=0):
    if mode == "lake":
        tables = jk.level2_lake(_recs("lake"), state["lut"], a, b, c)
    else:
        tables = jk.level2_stream(_recs("stream"), state["lut"], a, b, c, d)
    state["level2"] = tables
    return _js(tables)


def level2_csv():
    return jk.tables_csv(state.get("level2", []))


def chapman(m, c, r):
    return _js(jk.chapman_petersen(m, c, r))


# ---- files
def export_csv(mode, kind, meta):
    stem = jk.file_stem(_py(meta), mode)
    return _js({"name": f"{stem}_{kind}.csv", "text": jk.records_csv(_recs(mode), state["lut"], kind)})


def save(mode, meta):
    meta = _py(meta)
    stem = jk.file_stem(meta, mode)
    return _js({"name": f"{stem}_{meta.get('date') or 'survey'}.json",
                "text": jk.survey_json(mode, meta, _recs(mode))})


def load(text):
    try:
        mode, meta, recs = jk.read_survey(text)
    except ValueError as e:
        return _js({"ok": False, "error": str(e)})
    state["records"][mode] = recs
    return _js({"ok": True, "mode": mode, "meta": meta, "n": len(recs)})


def sample(mode):
    meta, recs = jk.sample_survey(mode)
    state["records"][mode] = recs
    return _js({"ok": True, "mode": mode, "meta": meta, "n": len(recs)})


api = js.Object.new()
for _name, _fn in {
    "lutGet": lut_get, "lutSet": lut_set, "lutReset": lut_reset, "species": species,
    "records": records, "add": add, "update": update, "remove": delete,
    "estimateWeights": estimate_weights, "lakeStats": lake_stats, "streamStats": stream_stats,
    "charts": charts, "level2": level2, "level2Csv": level2_csv, "chapman": chapman,
    "exportCsv": export_csv, "save": save, "load": load, "sample": sample,
}.items():
    setattr(api, _name, create_proxy(_fn))
window.Jake = api
window.dispatchEvent(js.CustomEvent.new("jake-ready"))
