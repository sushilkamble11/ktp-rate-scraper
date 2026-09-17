"""Render the dashboard (full HTML), the email (summary HTML), a CSV and a
GitHub job-summary markdown from the comparison results."""

import csv
import html
import io
import json
from datetime import date

import config

E = html.escape
VERDICT_LABEL = {"dearer": "KTP dearer", "cheaper": "KTP cheaper", "in line": "In line", "n/a": "No data"}
MATCH_LABEL = {"exact": "Exact match", "close": "Close match", "none": "No equivalent"}


def money(x, dp=0):
    if x is None:
        return "–"
    return f"${x:,.{dp}f}"


def signed_pct(x):
    if x is None:
        return "–"
    v = round(x)
    return "±0%" if v == 0 else f"{v:+d}%"


def signed_money(x):
    if x is None:
        return "–"
    return f"{'+' if x >= 0 else '−'}${abs(x):,.0f}"


def nice_date(iso):
    return date.fromisoformat(iso).strftime("%a %-d %b")


# ----------------------------------------------------------------- email ----

EMAIL_COLORS = {"dearer": ("#8a3b12", "#fbe7da"), "cheaper": ("#0f5a52", "#dcf1ee"),
                "in line": ("#3f4a45", "#eceeed"), "n/a": ("#8a8f8c", "#f4f4f4")}


def _email_chip(seg):
    if not seg:
        return '<span style="color:#8a8f8c">no data</span>'
    fg, bg = EMAIL_COLORS[seg["verdict"]]
    return (f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:10px;'
            f'font-weight:600;white-space:nowrap">{signed_pct(seg["pct"])}</span>'
            f'<br><span style="color:#6b716e;font-size:12px">KTP {money(seg["ktp_avg_night"])} vs '
            f'{money(seg["comp_avg_night"])}/night</span>')


def email_html(ctx):
    m = ctx["mapping"]
    comps = list(m["competitors"])
    td = 'style="padding:8px 10px;border-bottom:1px solid #e3e6e4;vertical-align:top"'
    th = 'style="padding:8px 10px;border-bottom:2px solid #1d3730;text-align:left;font-size:12px;color:#1d3730"'
    out = [f'<div style="font-family:-apple-system,Segoe UI,Arial,sans-serif;color:#1f2421;max-width:900px">'
           f'<h2 style="margin:0 0 4px;color:#1d3730">Competitor rates – {E(ctx["run_date_nice"])}</h2>'
           f'<p style="margin:0 0 16px;color:#6b716e">Next {config.DAYS_AHEAD} days · '
           f'% = how far KTP sits above (+) or below (−) the competitor\'s member price. '
           f'Within ±{config.IN_LINE_BAND_PCT}% counts as in line.</p>']
    if ctx["failures"]:
        out.append('<p style="background:#fde2e1;color:#8c1d18;padding:10px 12px;border-radius:6px">'
                   '<b>Some data is missing this week:</b> '
                   + E("; ".join(f"{k}: {v}" for k, v in ctx["failures"].items())) + '</p>')

    out.append('<table cellspacing="0" style="border-collapse:collapse;font-size:14px;width:100%">'
               f'<tr><th {th}>KTP category</th>')
    for c in comps:
        out.append(f'<th {th}>{E(m["competitors"][c]["short"])} weeknights</th>'
                   f'<th {th}>{E(m["competitors"][c]["short"])} weekends</th>')
    out.append('</tr>')
    by = {(s["cat"], s["comp"]): s for s in ctx["summary"]}
    for cat in m["categories"]:
        out.append(f'<tr><td {td}><b>{E(cat["label"])}</b></td>')
        for c in comps:
            s = by[(cat["key"], c)]
            if s["match"] == "none":
                out.append('<td colspan="2" style="padding:8px 10px;border-bottom:1px solid #e3e6e4;'
                           f'color:#8a8f8c">No equivalent at {E(m["competitors"][c]["short"])}</td>')
                continue
            tag = "" if s["match"] == "exact" else "*"
            out.append(f'<td {td}>{_email_chip(s["segments"]["weeknight"])}{tag}</td>'
                       f'<td {td}>{_email_chip(s["segments"]["weekend"])}{tag}</td>')
        out.append('</tr>')
    out.append('</table><p style="color:#6b716e;font-size:12px;margin:6px 0 0">'
               '* close match (same kind of product with a named difference) – see the mapping '
               'table in the attached dashboard. Weekends = Fri–Sun 2-night stays.</p>')

    # extras
    out.append('<h3 style="color:#1d3730;margin:24px 0 6px">Extra guest charges (per person, per night)</h3>'
               '<table cellspacing="0" style="border-collapse:collapse;font-size:14px">'
               f'<tr><th {th}>Category</th><th {th}>KTP adult / child</th>')
    for c in comps:
        out.append(f'<th {th}>{E(m["competitors"][c]["short"])} adult / child</th>')
    out.append('</tr>')
    for e in ctx["extras"]:
        out.append(f'<tr><td {td}>{E(e["label"])}</td>'
                   f'<td {td}>{money(e["ktp"]["adult"])} / {money(e["ktp"]["child"])}</td>')
        for c in comps:
            out.append(f'<td {td}>{money(e[c]["adult"])} / {money(e[c]["child"])}</td>')
        out.append('</tr>')
    out.append('</table>')

    moves = ctx["moves"]
    out.append('<h3 style="color:#1d3730;margin:24px 0 6px">Competitor price moves since last week</h3>')
    if ctx["prev_date"] is None:
        out.append('<p style="color:#6b716e">First run – nothing to compare yet.</p>')
    elif not moves:
        out.append(f'<p style="color:#6b716e">No moves of ${config.MOVE_MIN_DOLLARS}+ and '
                   f'{config.MOVE_MIN_PCT}%+ since {E(ctx["prev_date"])}.</p>')
    else:
        out.append(f'<p style="color:#6b716e;margin:0 0 6px">{len(moves)} changes since {E(ctx["prev_date"])}; '
                   'biggest 15 shown.</p><table cellspacing="0" style="border-collapse:collapse;font-size:14px">')
        for mv in moves[:15]:
            out.append(f'<tr><td {td}>{E(m["competitors"][mv["park"]]["short"])}</td><td {td}>{E(mv["room"])}</td>'
                       f'<td {td}>{E(nice_date(mv["check_in"]))} ({"2 nts" if mv["stay"] == "weekend" else "1 nt"})</td>'
                       f'<td {td}>{money(mv["was"])} → <b>{money(mv["now"])}</b> ({signed_pct(mv["pct"])})</td></tr>')
        out.append('</table>')
    out.append('<p style="color:#6b716e;font-size:12px;margin-top:24px">Full day-by-day detail is in the '
               'attached dashboard (open in a browser) and CSV. Price basis – KTP: '
               + E(m["ktp_price_basis"]) + '; '
               + E("; ".join(f'{v["short"]}: {v["price_basis"]}' for v in m["competitors"].values()))
               + '.</p></div>')
    return "".join(out)


# ------------------------------------------------------------------- csv ----

def csv_text(ctx):
    m = ctx["mapping"]
    comps = list(m["competitors"])
    buf = io.StringIO()
    w = csv.writer(buf)
    head = ["category", "stay", "check_in", "day", "nights", "ktp_price", "ktp_bookable", "ktp_note",
            "ktp_extra_adult_pn", "ktp_extra_child_pn"]
    for c in comps:
        head += [f"{c}_room", f"{c}_match", f"{c}_member_price", f"{c}_public_price", f"{c}_bookable",
                 f"{c}_note", f"{c}_estimated", f"ktp_vs_{c}_$", f"ktp_vs_{c}_%",
                 f"{c}_extra_adult_pn", f"{c}_extra_child_pn"]
    w.writerow(head)
    for r in ctx["rows"]:
        k = r["ktp"]
        line = [r["label"], r["stay"], r["check_in"], r["dow"], r["nights"], k["price"], k["bookable"],
                k["note"], k["extra_adult"], k["extra_child"]]
        for c in comps:
            x = r["comps"][c]
            line += [x["room"], x["match"], x["price"], x["rack"], x["bookable"], x["note"],
                     x["estimated"], x["diff"], x["pct"], x["extra_adult"], x["extra_child"]]
        w.writerow(line)
    return buf.getvalue()


# -------------------------------------------------------------- markdown ----

def markdown(ctx):
    m = ctx["mapping"]
    comps = list(m["competitors"])
    lines = [f"## Competitor rates – {ctx['run_date_nice']}", ""]
    if ctx["failures"]:
        lines += ["> **Missing data:** " + "; ".join(f"{k}: {v}" for k, v in ctx["failures"].items()), ""]
    hdr = "| Category | " + " | ".join(f"{m['competitors'][c]['short']} weeknights | "
                                        f"{m['competitors'][c]['short']} weekends" for c in comps) + " |"
    lines += [hdr, "|" + "---|" * (1 + 2 * len(comps))]
    by = {(s["cat"], s["comp"]): s for s in ctx["summary"]}
    for cat in m["categories"]:
        cells = []
        for c in comps:
            s = by[(cat["key"], c)]
            if s["match"] == "none":
                cells += ["no equivalent", ""]
                continue
            for seg in ("weeknight", "weekend"):
                st = s["segments"][seg]
                cells.append("–" if not st else
                             f"{signed_pct(st['pct'])} ({money(st['ktp_avg_night'])} vs {money(st['comp_avg_night'])})")
        lines.append(f"| {cat['label']} | " + " | ".join(cells) + " |")
    lines += ["", f"Records: " + ", ".join(f"{k} {v}" for k, v in ctx["counts"].items()),
              f"Competitor price moves since last run: {len(ctx['moves'])}"]
    return "\n".join(lines)


# ------------------------------------------------------------- dashboard ----

def dashboard_html(ctx):
    data = {
        "runDate": ctx["run_date"], "runDateNice": ctx["run_date_nice"], "prevDate": ctx["prev_date"],
        "days": config.DAYS_AHEAD, "band": config.IN_LINE_BAND_PCT,
        "mapping": ctx["mapping"], "summary": ctx["summary"], "monthly": ctx["monthly"],
        "extras": ctx["extras"], "moves": ctx["moves"], "rows": ctx["rows"],
        "failures": ctx["failures"], "counts": ctx["counts"], "headline": ctx["headline"],
    }
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return DASHBOARD_TEMPLATE.replace("/*__DATA__*/null", blob).replace(
        "__TITLE__", E(f"KTP competitor rates – {ctx['run_date_nice']}"))


DASHBOARD_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{
  --bg:#f6f3ec; --panel:#fffdf8; --ink:#1f2421; --muted:#68706b; --line:#e2ddd2;
  --brand:#1d3730; --brand-soft:#e6ede9;
  --dearer:#9a4515; --dearer-bg:#fbe8dc; --cheaper:#0f6158; --cheaper-bg:#dcf1ee;
  --inline:#46514b; --inline-bg:#eceeea; --na:#8b918d;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#121614; --panel:#1a201d; --ink:#e7ebe8; --muted:#9aa39e; --line:#2c3531;
    --brand:#9fd0bd; --brand-soft:#223029;
    --dearer:#f2a97c; --dearer-bg:#3a2519; --cheaper:#7fd3c6; --cheaper-bg:#16332f;
    --inline:#c3cbc6; --inline-bg:#262d2a; --na:#7b837f;
  }
}
:root[data-theme="dark"]{
  --bg:#121614; --panel:#1a201d; --ink:#e7ebe8; --muted:#9aa39e; --line:#2c3531;
  --brand:#9fd0bd; --brand-soft:#223029;
  --dearer:#f2a97c; --dearer-bg:#3a2519; --cheaper:#7fd3c6; --cheaper-bg:#16332f;
  --inline:#c3cbc6; --inline-bg:#262d2a; --na:#7b837f;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:0;color:var(--brand);letter-spacing:-.01em}
h2{font-size:17px;margin:34px 0 10px;color:var(--brand)}
.sub{color:var(--muted);margin:4px 0 0}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.alert{background:var(--dearer-bg);color:var(--dearer);border-radius:8px;padding:10px 14px;margin-top:16px;font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-top:20px}
.card h3{margin:0 0 8px;font-size:14px;color:var(--muted);font-weight:600}
.bar{display:flex;height:10px;border-radius:5px;overflow:hidden;background:var(--inline-bg);margin:8px 0}
.bar span{display:block}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--muted)}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:0}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:14px}
th{text-align:left;font-size:12px;color:var(--muted);font-weight:600;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.chip{display:inline-block;padding:2px 8px;border-radius:999px;font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap}
.dearer{color:var(--dearer);background:var(--dearer-bg)}
.cheaper{color:var(--cheaper);background:var(--cheaper-bg)}
.inline{color:var(--inline);background:var(--inline-bg)}
.na{color:var(--na)}
.small{font-size:12px;color:var(--muted)}
.badge{display:inline-block;font-size:11px;padding:1px 6px;border-radius:4px;border:1px solid var(--line);color:var(--muted);white-space:nowrap}
.badge.exact{border-color:transparent;background:var(--brand-soft);color:var(--brand)}
.controls{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 10px}
select,button{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:6px 10px}
button.on{background:var(--brand);color:var(--panel);border-color:var(--brand)}
.muted{color:var(--muted)}
.strike{opacity:.55}
.theme{float:right}
#summary{min-width:980px}#monthly,#extras{min-width:760px}#detail{min-width:560px}
@media (max-width:640px){h1{font-size:21px}.theme{float:none;margin-top:10px}}
</style>
</head>
<body>
<div class="wrap">
  <button class="theme" id="theme" type="button">Toggle theme</button>
  <h1 id="title"></h1>
  <p class="sub" id="subtitle"></p>
  <div id="alert"></div>
  <div class="cards" id="cards"></div>

  <h2>Where KTP sits, by category</h2>
  <p class="small">% = KTP price vs the competitor's member price for the same kind of stay, averaged per night over the window. <span id="bandnote"></span></p>
  <div class="panel scroll"><table id="summary"></table></div>

  <h2>By month</h2>
  <div class="controls"><select id="monthCat"></select></div>
  <div class="panel scroll"><table id="monthly"></table></div>

  <h2>Extra guest charges</h2>
  <p class="small">Per extra person, per night, above 2 adults (typical value across the window).</p>
  <div class="panel scroll"><table id="extras"></table></div>

  <h2>Competitor price moves</h2>
  <div class="panel scroll" id="moves"></div>

  <h2>Day by day</h2>
  <div class="controls">
    <select id="detCat"></select>
    <button type="button" data-stay="night" class="on">Single nights</button>
    <button type="button" data-stay="weekend">Fri–Sun weekends</button>
  </div>
  <div class="panel scroll"><table id="detail"></table></div>
  <p class="small">* estimated: that stay can't be booked as asked (usually a minimum-night rule), so the price is worked out from the nightly rate. Greyed = not bookable (sold out / min stay).</p>

  <h2>Category mapping</h2>
  <div class="panel scroll"><table id="mapping"></table></div>
  <p class="small" id="basis"></p>
</div>
<script>
const D = /*__DATA__*/null;
const M = D.mapping, COMPS = Object.keys(M.competitors);
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const money = (x, dp=0) => x == null ? "–" : "$" + Number(x).toLocaleString("en-AU", {minimumFractionDigits: dp, maximumFractionDigits: dp});
const pct = x => { if (x == null) return "–"; const v = Math.round(x); return (v > 0 ? "+" : v < 0 ? "−" : "±") + Math.abs(v) + "%"; };
const verdictOf = p => p == null ? "na" : p > D.band ? "dearer" : p < -D.band ? "cheaper" : "inline";
const VLABEL = {dearer: "KTP dearer", cheaper: "KTP cheaper", inline: "In line", na: "No data"};
const niceDate = iso => new Date(iso + "T00:00:00").toLocaleDateString("en-AU", {weekday: "short", day: "numeric", month: "short"});
const monthName = ym => new Date(ym + "-01T00:00:00").toLocaleDateString("en-AU", {month: "short", year: "numeric"});
const chip = p => `<span class="chip ${verdictOf(p)}">${pct(p)}</span>`;
const matchBadge = m => `<span class="badge ${m}">${{exact: "exact", close: "close", none: "no equivalent"}[m]}</span>`;

try { const t = localStorage.getItem("ktp-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) {}
$("#theme").onclick = () => {
  const cur = document.documentElement.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("ktp-theme", next); } catch (e) {}
};

$("#title").textContent = "Competitor rates – " + D.runDateNice;
$("#subtitle").textContent = `Next ${D.days} days · KTP vs ${COMPS.map(c => M.competitors[c].label).join(" and ")} · member prices`;
$("#bandnote").textContent = `Within ±${D.band}% = in line. Categories with no equivalent are shown for reference but not scored.`;
if (Object.keys(D.failures).length) {
  $("#alert").innerHTML = `<div class="alert">Missing data this run: ${esc(Object.entries(D.failures).map(([k, v]) => k + ": " + v).join("; "))}</div>`;
}

// headline cards
$("#cards").innerHTML = COMPS.map(c => {
  const h = D.headline[c] || {cheaper: 0, "in line": 0, dearer: 0};
  const tot = h.cheaper + h["in line"] + h.dearer || 1;
  const w = k => (h[k] / tot * 100).toFixed(1) + "%";
  return `<div class="panel card"><h3>vs ${esc(M.competitors[c].label)}</h3>
    <div><b>${h.dearer}</b> dearer · <b>${h["in line"]}</b> in line · <b>${h.cheaper}</b> cheaper</div>
    <div class="bar"><span class="dearer" style="width:${w("dearer")};background:var(--dearer)"></span><span style="width:${w("in line")};background:var(--inline)"></span><span style="width:${w("cheaper")};background:var(--cheaper)"></span></div>
    <div class="small">Count of category × (weeknight, weekend) comparisons</div></div>`;
}).join("") + `<div class="panel card"><h3>Reading the colours</h3><div class="legend">
  <span><i class="dot" style="background:var(--dearer)"></i>KTP more than ${D.band}% above</span>
  <span><i class="dot" style="background:var(--inline)"></i>within ±${D.band}%</span>
  <span><i class="dot" style="background:var(--cheaper)"></i>KTP more than ${D.band}% below</span></div>
  <div class="small" style="margin-top:8px">${D.prevDate ? "Compared with run on " + esc(D.prevDate) : "First run"} · ${Object.entries(D.counts).map(([k, v]) => esc(k) + " " + v).join(" · ")} records</div></div>`;

// summary
const byKey = {}; D.summary.forEach(s => byKey[s.cat + "|" + s.comp] = s);
const segCell = (st, ref) => !st ? `<td class="na">no data</td>` :
  `<td>${ref ? `<span class="muted">${pct(st.pct)}</span>` : chip(st.pct)}<div class="small">${money(st.ktp_avg_night)} vs ${money(st.comp_avg_night)} /nt · ${st.n} stays</div></td>`;
$("#summary").innerHTML = `<thead><tr><th>KTP category</th>${COMPS.map(c =>
  `<th>${esc(M.competitors[c].short)} room</th><th>Weeknights</th><th>Weekends (2 nts)</th>`).join("")}</tr></thead><tbody>` +
  M.categories.map(cat => `<tr><td><b>${esc(cat.label)}</b><div class="small">${esc(cat.ktp_spec)}</div></td>` +
    COMPS.map(c => {
      const s = byKey[cat.key + "|" + c], ref = s.match === "none";
      return `<td>${esc(s.room || "–")}<div>${matchBadge(s.match)}</div></td>` +
        segCell(s.segments.weeknight, ref) + segCell(s.segments.weekend, ref);
    }).join("") + `</tr>`).join("") + `</tbody>`;

// monthly
const catOpts = M.categories.map(c => `<option value="${c.key}">${esc(c.label)}</option>`).join("");
$("#monthCat").innerHTML = catOpts; $("#detCat").innerHTML = catOpts;
function renderMonthly() {
  const cat = $("#monthCat").value;
  const rows = D.monthly.filter(r => r.cat === cat);
  const months = [...new Set(rows.map(r => r.month))].sort();
  const get = (c, m, seg) => rows.find(r => r.comp === c && r.month === m && r.segment === seg);
  $("#monthly").innerHTML = `<thead><tr><th>Month</th>${COMPS.map(c =>
    `<th>${esc(M.competitors[c].short)} weeknights</th><th>${esc(M.competitors[c].short)} weekends</th>`).join("")}</tr></thead><tbody>` +
    (months.length ? months.map(m => `<tr><td>${monthName(m)}</td>` + COMPS.map(c => ["weeknight", "weekend"].map(seg => {
      const r = get(c, m, seg);
      if (!r) return `<td class="na">–</td>`;
      return `<td>${r.match === "none" ? `<span class="muted">${pct(r.pct)}</span>` : chip(r.pct)}<div class="small">${money(r.ktp_avg_night)} vs ${money(r.comp_avg_night)}</div></td>`;
    }).join("")).join("") + `</tr>`).join("") : `<tr><td class="na">No data</td></tr>`) + `</tbody>`;
}
$("#monthCat").onchange = renderMonthly; renderMonthly();

// extras
$("#extras").innerHTML = `<thead><tr><th>Category</th><th class="num">KTP adult</th><th class="num">KTP child</th>${COMPS.map(c =>
  `<th>${esc(M.competitors[c].short)} room</th><th class="num">Adult</th><th class="num">Child</th>`).join("")}</tr></thead><tbody>` +
  D.extras.map(e => `<tr><td>${esc(e.label)}</td><td class="num">${money(e.ktp.adult)}</td><td class="num">${money(e.ktp.child)}</td>` +
    COMPS.map(c => `<td class="small">${esc(e[c].room || "–")}</td><td class="num">${money(e[c].adult)}</td><td class="num">${money(e[c].child)}</td>`).join("") + `</tr>`).join("") + `</tbody>`;

// moves
if (!D.prevDate) $("#moves").innerHTML = `<p class="muted" style="margin:0">First run – next week's report will show what competitors changed.</p>`;
else if (!D.moves.length) $("#moves").innerHTML = `<p class="muted" style="margin:0">No moves of $10+ and 10%+ on mapped rooms since ${esc(D.prevDate)}.</p>`;
else $("#moves").innerHTML = `<table><thead><tr><th>Park</th><th>Room</th><th>Stay</th><th class="num">Was</th><th class="num">Now</th><th class="num">Change</th></tr></thead><tbody>` +
  D.moves.slice(0, 60).map(m => `<tr><td>${esc(M.competitors[m.park].short)}</td><td>${esc(m.room)}</td><td>${niceDate(m.check_in)} · ${m.stay === "weekend" ? "2 nts" : "1 nt"}</td><td class="num">${money(m.was)}</td><td class="num"><b>${money(m.now)}</b></td><td class="num">${pct(m.pct)}</td></tr>`).join("") +
  `</tbody></table>` + (D.moves.length > 60 ? `<p class="small">${D.moves.length - 60} more in the CSV.</p>` : "");

// detail
let stayFilter = "night";
document.querySelectorAll("button[data-stay]").forEach(b => b.onclick = () => {
  stayFilter = b.dataset.stay;
  document.querySelectorAll("button[data-stay]").forEach(x => x.classList.toggle("on", x === b));
  renderDetail();
});
const priceCell = (p, x) => {
  const cls = x.bookable ? "" : "strike";
  const title = [x.note, x.estimated ? "estimated" : ""].filter(Boolean).join(", ");
  return `<td class="num ${cls}" title="${esc(title)}">${money(p, p != null && p % 1 ? 2 : 0)}${x.estimated ? "*" : ""}${x.note ? `<div class="small">${esc(x.note)}</div>` : ""}</td>`;
};
function renderDetail() {
  const cat = $("#detCat").value;
  const rows = D.rows.filter(r => r.cat === cat && r.stay === stayFilter);
  $("#detail").innerHTML = `<thead><tr><th>Check-in</th><th class="num">KTP</th>${COMPS.map(c =>
    `<th class="num">${esc(M.competitors[c].short)}</th><th class="num">KTP vs</th>`).join("")}</tr></thead><tbody>` +
    rows.map(r => `<tr><td>${niceDate(r.check_in)}</td>${priceCell(r.ktp.price, r.ktp)}` +
      COMPS.map(c => { const x = r.comps[c];
        return priceCell(x.price, x) + `<td class="num">${x.pct == null ? "–" : (x.match === "none" ? `<span class="muted">${pct(x.pct)}</span>` : chip(x.pct))}</td>`;
      }).join("") + `</tr>`).join("") + `</tbody>`;
}
$("#detCat").onchange = renderDetail; renderDetail();

// mapping
$("#mapping").innerHTML = `<thead><tr><th>KTP</th>${COMPS.map(c => `<th>${esc(M.competitors[c].short)}</th>`).join("")}</tr></thead><tbody>` +
  M.categories.map(cat => `<tr><td><b>${esc(cat.label)}</b><div class="small">${esc(cat.ktp_spec)}</div></td>` +
    COMPS.map(c => { const m = cat.competitors[c] || {};
      return `<td>${esc(m.name || "–")} ${matchBadge(m.match || "none")}<div class="small">${esc(m.note || "")}</div></td>`; }).join("") + `</tr>`).join("") + `</tbody>`;
$("#basis").textContent = "Price basis – KTP: " + M.ktp_price_basis + ". " +
  COMPS.map(c => M.competitors[c].short + ": " + M.competitors[c].price_basis).join(". ") + ".";
</script>
</body>
</html>
"""
