"""Render the Rate Desk dashboard (HTML), the weekly email, a CSV and a
GitHub job-summary from the comparison results."""

import csv
import html
import io
import json
import os
from datetime import date

import config

E = html.escape
ST = {"open": "o", "sold out": "s", "min stay": "m", "not bookable": "b", "not open": "n"}


def money(x):
    return "–" if x is None else f"${x:,.0f}"


def spct(x):
    if x is None:
        return "–"
    v = round(x)
    return "±0%" if v == 0 else f"{v:+d}%"


def month_name(ym):
    return date.fromisoformat(ym + "-01").strftime("%b %Y")


def spans_text(spans):
    parts = []
    for a, b in spans:
        da, db = date.fromisoformat(a), date.fromisoformat(b)
        if a == b:
            parts.append(f"{da.day}")
        else:
            parts.append(f"{da.day}–{db.day}" if da.month == db.month else
                         f"{da.day} {da:%b}–{db.day} {db:%b}")
    return ", ".join(parts)


def action_line(a, comps):
    kind = "weekends" if a["weekend"] else "weeknights"
    return (f"{'Raise' if a['action'] == 'raise' else 'Lower'} {a['label']} – "
            f"{month_name(a['month'])} {kind} ({spans_text(a['spans'])}): "
            f"{money(a['ktp'])} → {money(a['suggest'])}")


# -------------------------------------------------------------- data blob ----

def _blob(ctx):
    m = ctx["mapping"]
    comps = list(m["competitors"])
    dates = sorted({r["date"] for r in ctx["rows"]})
    pos = {d: i for i, d in enumerate(dates)}
    grid = {c["key"]: [None] * len(dates) for c in m["categories"]}
    for r in ctx["rows"]:
        cell = [r["ktp"]["rate"], ST[r["ktp"]["status"]], r["ktp"]["units"]]
        for c in comps:
            cell += [r["comps"][c]["rate"], ST[r["comps"][c]["status"]]]
        cell += [None if r["market"] is None else round(r["market"], 2),
                 None if r["gap"] is None else round(r["gap"], 1),
                 r["action"] or "", ",".join(r["sold_out"])]
        grid[r["cat"]][pos[r["date"]]] = cell
    return {
        "run": {"date": ctx["run_date"], "nice": ctx["run_date_nice"],
                "generated": ctx.get("generated_at"), "prev": ctx["prev_date"], "note": ctx.get("note")},
        "cfg": {"band": config.IN_LINE_BAND_PCT, "raise": config.RAISE_GAP_PCT,
                "lower": config.LOWER_GAP_PCT, "round": config.ROUND_TO},
        "comps": m["competitors"], "ktpBasis": m["ktp_price_basis"],
        "cats": [{"key": c["key"], "label": c["label"], "spec": c["ktp_spec"],
                  "comps": {k: c["competitors"].get(k, {}) for k in comps}} for c in m["categories"]],
        "coverage": ctx["coverage"], "dates": dates, "grid": grid,
        "actions": ctx["actions"], "months": ctx["months"], "extras": ctx["extras"],
        "moves": ctx["moves"][:80], "failures": ctx["failures"], "counts": ctx["counts"],
    }


def dashboard_html(ctx, standalone=True):
    blob = json.dumps(_blob(ctx), separators=(",", ":")).replace("</", "<\\/")
    body = DASHBOARD.replace("/*__DATA__*/null", blob)
    if not standalone:            # hosted artifact: the host adds the document skeleton
        return body
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            f'{body}\n</body>\n</html>\n').replace("<!--HEAD-END-->", "</head>\n<body>", 1)


# ----------------------------------------------------------------- email ----

def email_html(ctx):
    m = ctx["mapping"]
    comps = list(m["competitors"])
    td = 'style="padding:7px 9px;border-bottom:1px solid #dfe4e1;vertical-align:top"'
    th = 'style="padding:7px 9px;border-bottom:2px solid #2e5e52;text-align:left;font-size:12px;color:#2e5e52"'
    o = ['<div style="font-family:-apple-system,Segoe UI,Arial,sans-serif;color:#16201c;max-width:860px">',
         f'<h2 style="margin:0 0 4px;color:#2e5e52">KTP Rate Desk – {E(ctx["run_date_nice"])}</h2>']
    if ctx["failures"]:
        o.append('<p style="background:#fbe3d6;color:#8a3a10;padding:9px 12px;border-radius:6px"><b>Missing data:</b> '
                 + E("; ".join(f"{k}: {v}" for k, v in ctx["failures"].items())) + '</p>')
    cov = ctx["coverage"]
    o.append('<p style="margin:0 0 14px;color:#5e6b65;font-size:13px">Rates loaded to: '
             + " · ".join(f'{"KTP" if p == "ktp" else m["competitors"][p]["short"]} {_d(cov[p]["priced_to"])}'
                          for p in ["ktp"] + comps if p in cov) + '</p>')
    for kind, title in (("raise", "Room to raise"), ("lower", "Priced above market")):
        acts = [a for a in ctx["actions"] if a["action"] == kind][:8]
        o.append(f'<h3 style="margin:18px 0 6px;color:{"#1d6fa5" if kind == "raise" else "#b4501c"}">{title}</h3>')
        if not acts:
            o.append('<p style="color:#5e6b65;margin:0">Nothing this week.</p>')
            continue
        o.append('<table cellspacing="0" style="border-collapse:collapse;font-size:14px;width:100%">'
                 f'<tr><th {th}>Category</th><th {th}>When</th><th {th}>KTP now</th><th {th}>Suggest</th>'
                 f'<th {th}>Market</th></tr>')
        for a in acts:
            when = f'{month_name(a["month"])} {"weekends" if a["weekend"] else "weeknights"}<br>' \
                   f'<span style="color:#5e6b65;font-size:12px">{E(spans_text(a["spans"]))}</span>'
            mk = " · ".join(f'{m["competitors"][c]["short"]} {money(a["comps"].get(c))}' for c in comps
                            if a["comps"].get(c) is not None)
            sold = f'<br><span style="color:#1d6fa5;font-size:12px">{", ".join(m["competitors"][s]["short"] for s in a["sold_out"])} sold out</span>' if a["sold_out"] else ""
            o.append(f'<tr><td {td}><b>{E(a["label"])}</b></td><td {td}>{when}</td>'
                     f'<td {td}>{money(a["ktp"])}</td><td {td}><b>{money(a["suggest"])}</b></td>'
                     f'<td {td}>{E(mk)}{sold}</td></tr>')
        o.append('</table>')
    if ctx["moves"]:
        o.append('<h3 style="margin:18px 0 6px;color:#2e5e52">Competitor price moves since last week</h3><ul style="margin:0;padding-left:18px">')
        for mv in ctx["moves"][:8]:
            o.append(f'<li>{E(m["competitors"][mv["park"]]["short"])} {E(mv["room"])}, {month_name(mv["month"])} '
                     f'({E(spans_text(mv["spans"]))}): {money(mv["was"])} → {money(mv["now"])}</li>')
        o.append('</ul>')
    o.append('<p style="color:#5e6b65;font-size:12px;margin-top:20px">Month-by-month view, opening-rate guide '
             'and extra-guest charges are in the attached dashboard (open in a browser).</p></div>')
    return "".join(o)


def _d(iso):
    return "–" if not iso else date.fromisoformat(iso).strftime("%-d %b %Y")


# ------------------------------------------------------------------- csv ----

def csv_text(ctx):
    m = ctx["mapping"]
    comps = list(m["competitors"])
    labels = {c["key"]: c["label"] for c in m["categories"]}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "day", "category", "ktp_rate", "ktp_status", "ktp_units"]
               + sum([[f"{c}_member_rate", f"{c}_status"] for c in comps], [])
               + ["market", "ktp_vs_market_%", "action"])
    for r in sorted(ctx["rows"], key=lambda r: (r["date"], r["cat"])):
        line = [r["date"], date.fromisoformat(r["date"]).strftime("%a"), labels[r["cat"]],
                r["ktp"]["rate"], r["ktp"]["status"], r["ktp"]["units"]]
        for c in comps:
            line += [r["comps"][c]["rate"], r["comps"][c]["status"]]
        line += [None if r["market"] is None else round(r["market"], 2),
                 None if r["gap"] is None else round(r["gap"], 1), r["action"] or ""]
        w.writerow(line)
    return buf.getvalue()


# -------------------------------------------------------------- markdown ----

def markdown(ctx):
    m = ctx["mapping"]
    comps = list(m["competitors"])
    cov = ctx["coverage"]
    lines = [f"## KTP Rate Desk – {ctx['run_date_nice']}", ""]
    if ctx["failures"]:
        lines += ["> **Missing data:** " + "; ".join(f"{k}: {v}" for k, v in ctx["failures"].items()), ""]
    lines += ["| Park | Rates loaded to | Taking bookings to |", "|---|---|---|"]
    for p in ["ktp"] + comps:
        if p in cov:
            name = "KTP" if p == "ktp" else m["competitors"][p]["short"]
            lines.append(f"| {name} | {_d(cov[p]['priced_to'])} | {_d(cov[p]['open_to'])} |")
    for kind, title in (("raise", "Room to raise"), ("lower", "Priced above market")):
        acts = [a for a in ctx["actions"] if a["action"] == kind][:10]
        lines += ["", f"### {title}", ""]
        lines += [f"- {action_line(a, comps)} (market {money(a['market'])}, {a['nights']} nights)" for a in acts] or ["- nothing"]
    lines += ["", f"Nightly records: " + ", ".join(f"{k} {v}" for k, v in ctx["counts"].items()),
              f"Competitor price moves since last run: {len(ctx['moves'])}"]
    return "\n".join(lines)


with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_template.html")) as _f:
    DASHBOARD = _f.read()
