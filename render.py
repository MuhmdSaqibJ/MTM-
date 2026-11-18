"""Terminal text, output.txt and report.html (the interface). Reads state only."""
import html, os
import core

money = lambda x: f"Rs {x:,.0f}"


def clock(P, off):
    st = P.get("start_time")
    try:
        h, m = map(int, str(st).split(":")[:2])
        off += h * 60 + m
        return f"{off // 60 % 24:02d}:{off % 60:02d}"
    except Exception:
        return f"T+{off // 60}:{off % 60:02d}"


def plan_lines(P, C):
    L = []
    if P["missing"]:
        return ["Plan incomplete. Missing facts: " + ", ".join(P["missing"])]
    v, f, J, B = P["venue"], P["food"], P["judging"], P["budget"]
    L.append(f"{P['students']} students, {P['teams']} teams, {P['people']} people on site")
    L.append("VENUE: " + (f"{v['name']} (seats {v['capacity']}, {money(v['price'])})" if v else "NONE FITS"))
    L.append("SCHEDULE:")
    for s in P["schedule"]:
        L.append(f"  {clock(P, s['start'])}-{clock(P, s['end'])}  {s['minutes']:>3} min  {s['name']}")
    if f:
        L.append(f"FOOD: {f['qty']} x {money(f['per_head'])} ({f['item']}) = {money(f['total'])}")
    L.append(f"JUDGING: {J['used']} judges needed of {J['confirmed']} confirmed; each covers {J['teams_per_judge']} teams "
             f"x {J['minutes_per_team']} min; honorarium total {money(J['cost'])}")
    L.append("BUDGET:")
    for n, a in B["lines"]:
        L.append(f"  {n:<44}{money(a):>14}")
    L.append(f"  {'TOTAL':<44}{money(B['cost']):>14}   (budget {money(B['total'])}, left {money(B['remaining'])})")
    for a in P["assumptions"]:
        L.append("Assumption: " + a)
    for a in P["warnings"]:
        L.append("WARNING: " + a)
    return L


def trace_text(state, start=0):
    out, calls, tok = [], 0, 0
    for t in state["trace"][start:]:
        if t["type"] == "call":
            calls += 1
            tok += t["total_tokens"]
            out += [f"--- MODEL CALL {t['n']} | model: {t['model']} | area: {t['area']} ---",
                    "INPUT:", t["input"].rstrip(), "OUTPUT:", t["output"].rstrip(),
                    f"TOKENS: input {t['prompt_tokens']} | output {t['output_tokens']} | thinking {t['thought_tokens']} | total {t['total_tokens']}", ""]
        else:
            out.append(f"  [{t['level']}] {t['text']}")
    total_all = sum(t["total_tokens"] for t in state["trace"] if t["type"] == "call")
    out.append(f"TOTAL TOKENS: {tok} in {calls} model call(s) this run | {total_all} across all runs")
    return "\n".join(out)


def full_text(state, start=None):
    _, sup, P, C = core.analyze(state)
    L = ["=== PLAN: " + ("VALID" if core.plan_ok(C) else "INVALID") + " ==="] + plan_lines(P, C)
    L += ["", "=== CHECKS ==="] + [f"[{'PASS' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}" for c in C]
    L += ["", "=== MESSAGES ==="]
    for r in core.message_rows(state, sup):
        L.append(f"#{r['n']} {r['sender']} {r['date'] or ''} [{r['status']}] {r['gist']} {('- ' + r['why']) if r['why'] else ''}")
    L += ["", "=== TRACE ===", trace_text(state, state["run_start"] if start is None else start)]
    return "\n".join(L)


CSS = """:root{
 --bg:#f5f7fb;--surface:#fff;--ink:#172033;--muted:#697586;--line:#e7ebf2;
 --accent:#3867e8;--accent-soft:#edf2ff;--green:#168451;--green-soft:#eaf7f0;
 --red:#c43d4b;--red-soft:#fff0f1;--amber:#946200;--amber-soft:#fff7e5;
 --shadow:0 8px 28px rgba(25,42,70,.055)
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.94);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.topbar{max-width:1180px;margin:auto;padding:15px 24px;display:flex;align-items:center;justify-content:space-between;gap:16px}
.brand{display:flex;align-items:center;gap:12px;min-width:0}
.mark{width:36px;height:36px;border-radius:11px;background:var(--accent);color:#fff;display:grid;place-items:center;font-weight:800;font-size:16px}
.brand-title{font-size:15px;font-weight:750;letter-spacing:-.02em}
.brand-sub{font-size:12px;color:var(--muted)}
.actions{display:flex;align-items:center;gap:9px}
main{max-width:1180px;margin:0 auto;padding:28px 24px 52px}
.hero{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-bottom:22px}
h1{font-size:25px;line-height:1.2;letter-spacing:-.04em;margin:0 0 6px}
h2{font-size:14px;letter-spacing:-.01em;margin:0;font-weight:750}
h3{font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin:0 0 12px}
.subtle{color:var(--muted);font-size:12px}
.pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:5px 10px;font-size:11px;font-weight:750;letter-spacing:.035em;white-space:nowrap}
.VALID,.PASS,.USED{background:var(--green-soft);color:var(--green)}
.INVALID,.FAIL,.REJECTED{background:var(--red-soft);color:var(--red)}
.IGNORED,.OUTDATED,.NOTAPPROVED,.WARNING{background:var(--amber-soft);color:var(--amber)}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin:18px 0}
.metric,.panel{background:var(--surface);border:1px solid var(--line);border-radius:15px;box-shadow:var(--shadow)}
.metric{padding:17px 18px;min-width:0}
.metric-label{font-size:12px;color:var(--muted);font-weight:600}
.metric-value{font-size:25px;font-weight:780;letter-spacing:-.045em;margin-top:5px;overflow-wrap:anywhere}
.metric-foot{font-size:11px;color:var(--muted);margin-top:3px}
.layout{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);gap:14px;margin-top:14px}
.panel{padding:18px;min-width:0}
.panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}
.check-list{display:grid;gap:0}
.check{display:flex;align-items:flex-start;gap:10px;padding:11px 0;border-bottom:1px solid var(--line)}
.check:last-child{border-bottom:0;padding-bottom:0}
.check-icon{width:21px;height:21px;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:800;flex:0 0 auto}
.check-icon.ok{background:var(--green-soft);color:var(--green)}
.check-icon.no{background:var(--red-soft);color:var(--red)}
.check-name{font-weight:700;font-size:13px}
.check-detail{font-size:12px;color:var(--muted);margin-top:2px}
.info-row{display:flex;justify-content:space-between;gap:14px;padding:10px 0;border-bottom:1px solid var(--line)}
.info-row:last-child{border-bottom:0}
.info-label{color:var(--muted);font-size:12px}
.info-value{text-align:right;font-weight:650;font-size:12px;overflow-wrap:anywhere}
table{width:100%;border-collapse:collapse}
th{text-align:left;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.07em;font-weight:750;padding:9px 10px;border-bottom:1px solid var(--line)}
td{padding:11px 10px;border-bottom:1px solid var(--line);vertical-align:top;font-size:12px}
tbody tr:last-child td{border-bottom:0}
.table-wrap{overflow-x:auto}
.schedule-time{white-space:nowrap;font-weight:700;color:var(--accent)}
.money{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.total-row td{font-weight:800;border-top:1px solid var(--line)}
.budget-bar{height:8px;border-radius:99px;background:#edf0f5;overflow:hidden;margin:13px 0 7px}
.budget-fill{height:100%;background:var(--accent);border-radius:99px;max-width:100%}
.budget-meta{display:flex;justify-content:space-between;gap:12px;font-size:11px;color:var(--muted)}
.assumption{padding:8px 10px;background:#f8f9fc;border-radius:9px;font-size:11px;color:var(--muted);margin-top:8px}
.warning{padding:9px 11px;border-radius:9px;background:var(--amber-soft);color:var(--amber);font-size:11px;margin-top:8px}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
input,select{font:inherit;border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:9px;padding:8px 10px;font-size:12px;outline:none}
input:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
input{min-width:190px}
.messages{margin-top:14px}
.trace{margin-top:14px}
details{border-top:1px solid var(--line);padding:11px 0}
details:first-of-type{border-top:0}
summary{cursor:pointer;font-size:12px;font-weight:650}
pre{white-space:pre-wrap;word-break:break-word;background:#f7f8fb;border:1px solid var(--line);padding:12px;border-radius:10px;max-height:300px;overflow:auto;font:11px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace}
.empty{padding:22px;text-align:center;color:var(--muted);font-size:12px}
.btn{border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:9px;padding:8px 11px;font-size:12px;font-weight:650;cursor:pointer}
.btn:hover{background:#f7f8fb}
.footer{text-align:center;color:var(--muted);font-size:11px;padding:22px 0 0}
@media(max-width:850px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.layout{grid-template-columns:1fr}}
@media(max-width:560px){.topbar{padding:12px 15px}main{padding:21px 14px 36px}.hero{align-items:flex-start;flex-direction:column}h1{font-size:22px}.metrics{gap:9px}.metric{padding:13px}.metric-value{font-size:21px}.panel{padding:14px}.brand-sub{display:none}.actions .subtle{display:none}}
@media print{body{background:#fff}.topbar{position:static}.actions{display:none}main{padding:12px;max-width:none}.metric,.panel{box-shadow:none;break-inside:avoid}.trace{display:none}}
"""


def html_report(state):
    e = html.escape
    _, sup, P, C = core.analyze(state)
    ok = core.plan_ok(C)
    rows = core.message_rows(state, sup)
    trace = state.get("trace", [])

    def pill(value):
        clean = str(value).replace(" ", "")
        return f"<span class='pill {e(clean)}'>{e(str(value))}</span>"

    checks_html = "".join(
        f"<div class='check'><span class='check-icon {'ok' if c['ok'] else 'no'}'>{'✓' if c['ok'] else '!'}</span>"
        f"<div><div class='check-name'>{e(c['name'])}</div><div class='check-detail'>{e(c['detail'])}</div></div></div>"
        for c in C
    ) or "<div class='empty'>No checks available.</div>"

    if not P["missing"]:
        v, f, J, B = P["venue"], P["food"], P["judging"], P["budget"]
        venue_name = f"{e(str(v['name']))} · {v['capacity']} seats" if v else "No suitable venue"
        food_line = f"{f['qty']} × {money(f['per_head'])} · {e(str(f['item']))}"
        schedule_html = "".join(
            f"<tr><td class='schedule-time'>{e(clock(P, s['start']))} – {e(clock(P, s['end']))}</td>"
            f"<td>{s['minutes']} min</td><td>{e(str(s['name']))}</td></tr>"
            for s in P["schedule"]
        ) or "<tr><td colspan='3' class='empty'>No schedule items.</td></tr>"
        budget_rows = "".join(
            f"<tr><td>{e(str(n))}</td><td class='money'>{money(a)}</td></tr>" for n, a in B["lines"]
        )
        budget_total = B["total"]
        used_pct = max(0, min(100, (B["cost"] / B["total"] * 100) if B["total"] else 0))
        plan_content = (
            f"<div class='info-row'><span class='info-label'>Venue</span><span class='info-value'>{venue_name} · {money(v['price']) if v else '—'}</span></div>"
            f"<div class='info-row'><span class='info-label'>Food</span><span class='info-value'>{food_line} = {money(f['total'])}</span></div>"
            f"<div class='info-row'><span class='info-label'>Judging</span><span class='info-value'>{J['used']} / {J['confirmed']} judges · {money(J['cost'])}</span></div>"
            f"<div class='info-row'><span class='info-label'>People on site</span><span class='info-value'>{P['people']}</span></div>"
            f"<div class='info-row'><span class='info-label'>Teams</span><span class='info-value'>{P['teams']}</span></div>"
        )
        schedule_panel = (
            "<section class='panel'><div class='panel-head'><h2>Event schedule</h2><span class='subtle'>Run of show</span></div>"
            f"<div class='table-wrap'><table><thead><tr><th>Time</th><th>Duration</th><th>Activity</th></tr></thead><tbody>{schedule_html}</tbody></table></div></section>"
        )
        budget_panel = (
            "<section class='panel'><div class='panel-head'><h2>Budget overview</h2><span class='subtle'>Estimated costs</span></div>"
            f"<div class='table-wrap'><table><tbody>{budget_rows}"
            f"<tr class='total-row'><td>Total planned</td><td class='money'>{money(B['cost'])}</td></tr>"
            f"<tr><td class='info-label'>Budget remaining</td><td class='money'>{money(B['remaining'])}</td></tr></tbody></table></div>"
            f"<div class='budget-bar'><div class='budget-fill' style='width:{used_pct:.1f}%'></div></div>"
            f"<div class='budget-meta'><span>{used_pct:.1f}% of budget allocated</span><span>Budget: {money(budget_total)}</span></div>"
            + "".join(f"<div class='assumption'>Assumption · {e(str(a))}</div>" for a in P["assumptions"])
            + "".join(f"<div class='warning'>Note · {e(str(a))}</div>" for a in P["warnings"])
            + "</section>"
        )
        metrics = (
            f"<div class='metric'><div class='metric-label'>Students</div><div class='metric-value'>{P['students']:,}</div><div class='metric-foot'>Registered participants</div></div>"
            f"<div class='metric'><div class='metric-label'>Teams</div><div class='metric-value'>{P['teams']:,}</div><div class='metric-foot'>Based on team size</div></div>"
            f"<div class='metric'><div class='metric-label'>People on site</div><div class='metric-value'>{P['people']:,}</div><div class='metric-foot'>Participants and staff</div></div>"
            f"<div class='metric'><div class='metric-label'>Budget remaining</div><div class='metric-value'>{money(B['remaining'])}</div><div class='metric-foot'>Of {money(B['total'])} total budget</div></div>"
        )
    else:
        missing = ", ".join(e(str(x)) for x in P["missing"])
        plan_content = f"<div class='empty'>The plan is incomplete. Missing information: {missing}</div>"
        schedule_panel = "<section class='panel'><div class='panel-head'><h2>Event schedule</h2></div><div class='empty'>Available once required information is supplied.</div></section>"
        budget_panel = "<section class='panel'><div class='panel-head'><h2>Budget overview</h2></div><div class='empty'>Available once required information is supplied.</div></section>"
        metrics = (
            f"<div class='metric'><div class='metric-label'>Plan status</div><div class='metric-value'>Incomplete</div><div class='metric-foot'>Some required facts are missing</div></div>"
            f"<div class='metric'><div class='metric-label'>Messages</div><div class='metric-value'>{len(rows)}</div><div class='metric-foot'>Processed inputs</div></div>"
        )

    message_rows = "".join(
        f"<tr data-status='{e(str(r['status']).upper())}'><td>{r['n']}</td>"
        f"<td><b>{e(str(r['sender']))}</b><div class='subtle'>{e(str(r['date'] or ''))}</div></td>"
        f"<td>{e(str(r['gist']))}</td><td>{pill(r['status'])}</td><td class='subtle'>{e(str(r['why']))}</td></tr>"
        for r in rows
    )
    if not message_rows:
        message_rows = "<tr><td colspan='5' class='empty'>No messages have been recorded.</td></tr>"

    trace_html = []
    total_tokens = 0
    for t in trace:
        if t["type"] == "call":
            total_tokens += t.get("total_tokens", 0)
            trace_html.append(
                f"<details><summary>Model call {t['n']} · {e(str(t['model']))} · {e(str(t['area']))} "
                f"<span class='subtle'>· {t.get('total_tokens', 0):,} tokens</span></summary>"
                f"<p class='subtle'>Input {t.get('prompt_tokens', 0):,} · Output {t.get('output_tokens', 0):,} · "
                f"Thinking {t.get('thought_tokens', 0):,}</p><b class='subtle'>Input</b><pre>{e(str(t.get('input', '')))}</pre>"
                f"<b class='subtle'>Output</b><pre>{e(str(t.get('output', '')))}</pre></details>"
            )
        else:
            level = str(t.get("level", "INFO"))
            cls = {"REJECTED": "REJECTED", "PLAN": "VALID" if "INVALID" not in str(t.get("text", "")) else "INVALID"}.get(level, "IGNORED")
            trace_html.append(
                f"<div class='check'><div>{pill(level)}</div><div class='check-detail'>{e(str(t.get('text', '')))}</div></div>"
            )

    h = [
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='refresh' content='4'><title>Mind to Machine · Event dashboard</title>"
        f"<style>{CSS}</style></head><body>",
        "<header><div class='topbar'><div class='brand'><div class='mark'>M</div>"
        "<div><div class='brand-title'>Mind to Machine</div><div class='brand-sub'>Event planning dashboard</div></div></div>"
        "<div class='actions'><span class='subtle'>Auto-refresh · 4 seconds</span>"
        "<button class='btn' onclick='window.print()'>Export / Print</button></div></div></header>",
        "<main><div class='hero'><div><h1>Event overview</h1>"
        f"<div class='subtle'>Live plan summary · Model: {e(str(core.model_name()))}</div></div>{pill('VALID' if ok else 'INVALID')}</div>",
        f"<div class='metrics'>{metrics}</div>",
        "<div class='layout'><section class='panel'><div class='panel-head'><h2>Validation checks</h2>"
        f"<span class='subtle'>{sum(1 for c in C if c['ok'])} of {len(C)} passed</span></div><div class='check-list'>{checks_html}</div></section>",
        f"<section class='panel'><div class='panel-head'><h2>Planning details</h2><span class='subtle'>Current calculated plan</span></div>{plan_content}</section></div>",
        f"<div class='layout'>{schedule_panel}{budget_panel}</div>",
        "<section class='panel messages'><div class='panel-head'><div><h2>Incoming messages</h2>"
        f"<div class='subtle'>{len(rows)} messages · latest interpreted status</div></div>"
        "<div class='toolbar'><input id='messageSearch' type='search' placeholder='Search messages…' aria-label='Search messages'>"
        "<select id='statusFilter' aria-label='Filter by status'><option value=''>All statuses</option>"
        "<option value='USED'>Used</option><option value='REJECTED'>Rejected</option><option value='IGNORED'>Ignored</option>"
        "<option value='OUTDATED'>Outdated</option></select></div></div>"
        f"<div class='table-wrap'><table id='messageTable'><thead><tr><th>#</th><th>Sender</th><th>Message summary</th><th>Status</th><th>Reason</th></tr></thead><tbody>{message_rows}</tbody></table></div></section>",
        "<section class='panel trace'><div class='panel-head'><div><h2>AI activity</h2>"
        f"<div class='subtle'>{sum(1 for t in trace if t['type'] == 'call')} model calls · {total_tokens:,} total tokens across all runs</div></div>"
        "<span class='subtle'>Expand to inspect</span></div>",
        "".join(trace_html) if trace_html else "<div class='empty'>No model activity recorded.</div>",
        "</section><div class='footer'>Mind to Machine · Calculations and validation are performed by the planning code.</div></main>",
        """<script>
const searchBox=document.getElementById('messageSearch');
const statusBox=document.getElementById('statusFilter');
function filterMessages(){
 const q=(searchBox.value||'').toLowerCase();
 const status=statusBox.value;
 document.querySelectorAll('#messageTable tbody tr[data-status]').forEach(row=>{
  const matchesText=row.innerText.toLowerCase().includes(q);
  const matchesStatus=!status||row.dataset.status.replaceAll(' ','')===status;
  row.hidden=!(matchesText&&matchesStatus);
 });
}
searchBox.addEventListener('input',filterMessages);
statusBox.addEventListener('change',filterMessages);
</script></body></html>"""
    ]
    return "".join(h)


def emit(state):
    text = full_text(state)
    print("\n" + text)
    with open("output.txt", "w", encoding="utf-8") as f:
        f.write(full_text(state, start=0))
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html_report(state))
