"""PyScript bridge between the WaTSS page (JavaScript plots and controls) and watss.py.

Holds the loaded record and the current filtered series in Python, and exposes a
small API on window.WaTSS that the page calls. All analysis lives in watss.py.
"""

import math

import js
from pyodide.ffi import create_proxy, to_js
from pyscript import window

import watss

state = {"name": "", "t": [], "y": [], "dt": watss.HOUR, "unit": "F", "low": ([], [])}


def _js(obj):
    return to_js(obj, dict_converter=js.Object.fromEntries)


def load(text, name, fallback_unit):
    """Parse a file; keep it as the current record. Returns the raw series for plotting."""
    d = watss.parse(text)
    if len(d["t"]) < 2:
        return _js({"ok": False})
    state.update(name=name, t=d["t"], y=d["y"], dt=d["dt"], unit=d["unit"] or fallback_unit)
    return _js({"ok": True, "t": d["t"], "y": d["y"], "dt": d["dt"], "ampm": d["ampm"],
                "unit": state["unit"], "unitFromFile": d["unit"] is not None})


def set_unit(unit):
    state["unit"] = unit


def set_filter(filt, averaging, win):
    t, y = watss.filter_series(state["t"], state["y"], filt, averaging, int(win))
    state["low"] = (t, y)
    return _js({"t": t, "y": y})


def stats(t_left, t_right):
    return _js(watss.compute_stats(state["t"], state["y"], state["unit"], state["dt"], t_left, t_right))


def thresholds(system):
    return _js([list(row) for row in watss.thresholds(system)])


def export(t_left, t_right, filt, averaging, win):
    t, y = state["low"]
    return _js({"name": watss.export_name(state["name"], filt, averaging, win),
                "text": watss.export_text(state["name"], t, y, t_left, t_right)})


def r_code(t_left, t_right, filt, averaging, win, x0, x1, ry0, ry1, ly0, ly1):
    """Zip of ggplot2 code + tidy data. Missing zoom / y-limits come in as NaN."""
    def pair(a, b):
        return None if math.isnan(a) or math.isnan(b) else (a, b)
    t, y = state["low"]
    name, data = watss.r_bundle(state["name"], state["unit"], state["t"], state["y"], t, y, state["dt"],
                                filt, averaging, int(win), t_left, t_right,
                                pair(x0, x1), pair(ry0, ry1), pair(ly0, ly1))
    buf = js.Uint8Array.new(len(data))
    buf.assign(data)
    out = js.Object.new()
    out.name, out.data = name, buf
    return out


def sample():
    return watss.sample_csv()


api = js.Object.new()
for _name, _fn in {"load": load, "setUnit": set_unit, "setFilter": set_filter, "stats": stats,
                   "thresholds": thresholds, "export": export, "rCode": r_code, "sample": sample}.items():
    setattr(api, _name, create_proxy(_fn))
window.WaTSS = api
window.dispatchEvent(js.CustomEvent.new("watss-ready"))
