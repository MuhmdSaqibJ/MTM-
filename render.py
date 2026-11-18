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


CSS = """:root{--bg:#f6f7f9;--card:#fff;--text:#1b1f24;--muted:#5d6672;--line:#dfe3e8;--ok:#1b6e3a;--okbg:#e5f6ea;--bad:#c62828;--badbg:#fdecec;--warn:#8a5a00;--warnbg:#fff4d6;--acc:#1f6feb;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root{--bg:#111418;--card:#1b2027;--text:#e8ebef;--muted:#9aa4b0;--line:#2c333c;--ok:#7ee2a0;--okbg:#16301f;--bad:#ff8a80;--badbg:#3a1d1d;--warn:#ffd27a;--warnbg:#3a2f14;--acc:#58a6ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,sans-serif}
main{max-width:980px;margin:0 auto;padding:16px}h1{margin:0 0 4px}h2{margin:0 0 8px;font-size:1.05rem}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));margin-top:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;overflow-x:auto}
table{border-collapse:collapse;width:100%}td,th{padding:4px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.b{display:inline-block;border-radius:999px;padding:1px 10px;font-size:.8rem;font-weight:600}
.PASS,.USED,.VALID{background:var(--okbg);color:var(--ok)}.FAIL,.REJECTED,.INVALID{background:var(--badbg);color:var(--bad)}
.IGNORED,.OUTDATED,.NOTAPPROVED{background:var(--warnbg);color:var(--warn)}
pre{white-space:pre-wrap;word-break:break-word;background:var(--bg);padding:8px;border-radius:8px;max-height:260px;overflow:auto;font-size:.8rem}
.muted{color:var(--muted)}.note{padding:4px 0;border-bottom:1px solid var(--line)}"""


def html_report(state):
    e = html.escape
    _, sup, P, C = core.analyze(state)
    ok = core.plan_ok(C)
    h = [f"<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<meta http-equiv='refresh' content='4'><title>Event plan</title><style>{CSS}</style></head><body><main>",
         f"<h1>Mind to Machine: event plan <span class='b {'VALID' if ok else 'INVALID'}'>{'VALID' if ok else 'INVALID'}</span></h1>"
         f"<div class='muted'>Model: {e(core.model_name())}. The model only reads messages; code plans and checks. Page refreshes every 4 s.</div>"]
    h.append("<div class='grid'><div class='card'><h2>Checks</h2><table>" + "".join(
        f"<tr><td><span class='b {'PASS' if c['ok'] else 'FAIL'}'>{'PASS' if c['ok'] else 'FAIL'}</span></td><td><b>{e(c['name'])}</b><br><span class='muted'>{e(c['detail'])}</span></td></tr>"
        for c in C) + "</table></div>")
    if not P["missing"]:
        v, f, J, B = P["venue"], P["food"], P["judging"], P["budget"]
        h.append("<div class='card'><h2>Venue, food, judging</h2>"
                 f"<p><b>Venue:</b> {e(str(v['name'])) + ' (seats ' + str(v['capacity']) + ', ' + money(v['price']) + ')' if v else 'none fits'}</p>"
                 f"<p><b>Food:</b> {f['qty']} x {money(f['per_head'])} ({e(f['item'])}) = {money(f['total'])}</p>"
                 f"<p><b>Judging:</b> {J['used']} judges of {J['confirmed']} confirmed; each covers {J['teams_per_judge']} teams x {J['minutes_per_team']} min; honorarium {money(J['cost'])}</p>"
                 f"<p class='muted'>{P['students']} students, {P['teams']} teams, {P['people']} people on site</p></div>")
        h.append("<div class='card'><h2>Schedule</h2><table>" + "".join(
            f"<tr><td>{clock(P, s['start'])}-{clock(P, s['end'])}</td><td>{s['minutes']} min</td><td>{e(s['name'])}</td></tr>" for s in P["schedule"]) + "</table></div>")
        h.append("<div class='card'><h2>Budget</h2><table>" + "".join(
            f"<tr><td>{e(n)}</td><td style='text-align:right'>{money(a)}</td></tr>" for n, a in B["lines"])
            + f"<tr><th>Total</th><th style='text-align:right'>{money(B['cost'])}</th></tr>"
            f"<tr><td class='muted'>Budget / left</td><td class='muted' style='text-align:right'>{money(B['total'])} / {money(B['remaining'])}</td></tr></table>"
            + "".join(f"<p class='muted'>Assumption: {e(a)}</p>" for a in P["assumptions"])
            + "".join(f"<p><b>Warning:</b> {e(a)}</p>" for a in P["warnings"]) + "</div>")
    else:
        h.append(f"<div class='card'><h2>Plan incomplete</h2><p>Missing facts: {e(', '.join(P['missing']))}</p></div>")
    h.append("</div><div class='card' style='margin-top:12px'><h2>Messages</h2><table><tr><th>#</th><th>From</th><th>Gist</th><th>Status</th><th>Why</th></tr>" + "".join(
        f"<tr><td>{r['n']}</td><td>{e(r['sender'])} <span class='muted'>{e(r['date'] or '')}</span></td><td>{e(r['gist'])}</td>"
        f"<td><span class='b {r['status'].replace(' ', '')}'>{r['status']}</span></td><td class='muted'>{e(r['why'])}</td></tr>"
        for r in core.message_rows(state, sup)) + "</table></div>")
    h.append("<div class='card' style='margin-top:12px'><h2>Trace (all runs)</h2>")
    for t in state["trace"]:
        if t["type"] == "call":
            h.append(f"<details><summary><b>Call {t['n']}</b> | {e(t['model'])} | area: {e(t['area'])} | tokens in {t['prompt_tokens']} / out {t['output_tokens']} / thinking {t['thought_tokens']} / total {t['total_tokens']}</summary>"
                     f"<b>Input</b><pre>{e(t['input'])}</pre><b>Output</b><pre>{e(t['output'])}</pre></details>")
        else:
            cls = {"REJECTED": "REJECTED", "PLAN": "VALID" if "INVALID" not in t["text"] else "INVALID"}.get(t["level"], "IGNORED")
            h.append(f"<div class='note'><span class='b {cls}'>{e(t['level'])}</span> {e(t['text'])}</div>")
    tot = sum(t["total_tokens"] for t in state["trace"] if t["type"] == "call")
    h.append(f"<p><b>Total tokens: {tot}</b></p></div></main></body></html>")
    return "".join(h)


def emit(state):
    text = full_text(state)
    print("\n" + text)
    with open("output.txt", "w", encoding="utf-8") as f:
        f.write(full_text(state, start=0))
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html_report(state))
