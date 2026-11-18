"""Event planner core.

Design: the model ONLY READS messy text (area "reading") and returns structured facts.
Plain code does all arithmetic, planning, validation, supersession and rollback.
No pack facts are typed in this file.
"""
import copy, datetime, json, math, os, re, time, urllib.error, urllib.request

STATE_FILE = "state.json"
LISTS = ("venues", "food", "food_orders", "spent", "sessions", "constraints", "proposals")
AREAS = ("venue", "schedule", "food", "judging", "budget")
# Schedule defaults: used ONLY when no message defines that session. Shown as assumptions.
DEF_OPENING, DEF_LUNCH, DEF_CLOSING, DEF_MIN_BUILD = 10, 30, 15, 60

PROMPT = """You read event-planning messages (English or Roman Urdu, any format) and return ONLY JSON.
Number messages from @@START@@ in the order given (keep a number if the text shows one).
Schema:
{"messages":[{"n":1,"sender":"","date":"YYYY-MM-DD or null","gist":"max 8 words","relevant":true,"note":"why not relevant, else empty"}],
"event":[{"field":F,"value":V,"msg":n}],
"venues":[{"name":"","capacity":0,"price":0,"features":[],"msg":n}],
"food":[{"item":"","price_per_head":0,"msg":n}],
"food_orders":[{"item":"","quantity":0,"msg":n}],
"spent":[{"item":"","amount":0,"msg":n}],
"sessions":[{"name":"","minutes":0,"msg":n}],
"constraints":[{"type":T,"value":V,"text":"","msg":n}],
"proposals":[{"item":"","cost":0,"msg":n}]}
F is one of: students, team_size, duration_hours, staff, budget_total, judges_confirmed, honorarium, minutes_per_team, max_teams_per_judge, start_time (HH:MM 24h).
T is one of: venue_feature (value = needed feature, e.g. generator), budget_reserve_pct, budget_reserve_amount, max_cost_food, max_cost_venue, max_cost_judging, min_build_minutes, other (put the rule in text).
Rules: copy numbers exactly as plain numbers (PKR, minutes, people); never calculate. Year is 2026.
sessions = fixed breaks or ceremonies the schedule must contain. spent = money already committed from the budget.
food_orders = a number of meals someone says they ordered or will deliver. proposals = requests or quotes nobody approved.
relevant=false only for chatter that states no rule, price or number. Every message gets an entry in messages.
Messages:
"""


def load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def model_name():
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")


def num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        m = re.search(r"-?\d[\d,]*\.?\d*", str(v))
        if not m:
            return None
        x = float(m.group().replace(",", ""))
    return int(x) if x.is_integer() else x


# ---------------------------------------------------------------- state / trace
def new_state():
    return {"messages": {}, "facts": [], "rejected": {}, "trace": [], "noted": [],
            "next_msg": 1, "run_start": 0}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def load_state():
    with open(STATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def note(state, level, text):
    state["trace"].append({"type": "note", "level": level, "text": text})


# ---------------------------------------------------------------- the one model call type
def call_model(state, area, prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("Missing GEMINI_API_KEY. Put it in a .env file: GEMINI_API_KEY=your_key")
    name = model_name()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{name}:generateContent"
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    data = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "x-goog-api-key": key})
            with urllib.request.urlopen(req, timeout=50) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as ex:
            if ex.code in (429, 500, 503) and attempt < 2:
                time.sleep(2 + 2 * attempt)
                continue
            raise SystemExit(f"Model error {ex.code}: {ex.read().decode()[:300]}")
        except urllib.error.URLError as ex:
            if attempt < 2:
                time.sleep(2)
                continue
            raise SystemExit(f"Network error: {ex}")
    parts = data["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    u = data.get("usageMetadata", {})
    pt, ot, th = u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0), u.get("thoughtsTokenCount", 0)
    tt = u.get("totalTokenCount", pt + ot + th)
    n = 1 + sum(1 for t in state["trace"] if t["type"] == "call")
    state["trace"].append({"type": "call", "n": n, "model": name, "area": area, "input": prompt,
                           "output": text, "prompt_tokens": pt, "output_tokens": ot,
                           "thought_tokens": th, "total_tokens": tt})
    return text


def extract(state, raw, start):
    text = call_model(state, "reading", PROMPT.replace("@@START@@", str(start)) + raw)
    try:
        clean = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
        return json.loads(clean)
    except Exception as ex:
        note(state, "ERROR", f"Model output was not valid JSON ({ex}). Nothing was changed.")
        return {}


# ---------------------------------------------------------------- facts
def fkey(f):
    L = f["list"]
    if L == "event":
        return str(f.get("field", "")).lower()
    if L in ("venues", "sessions"):
        return str(f.get("name", "")).strip().lower()
    if L == "constraints":
        t = str(f.get("type", "")).lower()
        if t == "venue_feature":
            return t + ":" + str(f.get("value", "")).lower()
        if t == "other":
            return t + ":" + str(f.get("text", "")).lower()
        return t
    return str(f.get("item", "")).strip().lower()


def describe(f):
    L = f["list"]
    g = f.get
    if L == "event": return f"{g('field')} = {g('value')}"
    if L == "venues": return f"{g('name')} (seats {g('capacity')}, Rs {g('price')})"
    if L == "food": return f"{g('item')} meal Rs {g('price_per_head')}/head"
    if L == "food_orders": return f"{g('quantity')} x {g('item')} meals ordered"
    if L == "spent": return f"{g('item')} already spent Rs {g('amount')}"
    if L == "sessions": return f"{g('name')} {g('minutes')} min"
    if L == "constraints": return f"{g('type')}: {g('value') or g('text')}"
    return f"{g('item')} proposal Rs {g('cost')}"


def add_extraction(state, ex, update, raw):
    msgs = ex.get("messages") or []
    if update and not msgs:
        msgs = [{"n": state["next_msg"], "sender": "new message", "relevant": True}]
    idmap = {}
    for i, m in enumerate(msgs):
        try:
            n = int(m.get("n"))
        except (TypeError, ValueError):
            n = i + 1
        if update:
            new = state["next_msg"]
            state["next_msg"] += 1
        else:
            new = n
        idmap[n] = new
        d = m.get("date")
        d = d if isinstance(d, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) else None
        state["messages"][str(new)] = {
            "n": new, "sender": m.get("sender") or "?", "date": d, "gist": m.get("gist") or "",
            "relevant": bool(m.get("relevant", True)), "note": m.get("note") or "",
            "ord": f"{d or ('9999-99-99' if update else '0000-00-00')}|{new:05d}",
            "text": raw if update else ""}
    last = list(idmap.values())[-1] if idmap else None
    for L in ("event",) + LISTS:
        for it in ex.get(L) or []:
            if not isinstance(it, dict):
                continue
            try:
                mid = idmap.get(int(it.get("msg")))
            except (TypeError, ValueError):
                mid = None
            if mid is None and update:
                mid = last
            if mid is None:
                continue
            state["facts"].append({**it, "list": L, "msg": mid})
    if not update:
        state["next_msg"] = max(idmap.values(), default=0) + 1
    return list(idmap.values())


def build_world(state):
    msgs, groups = state["messages"], {}
    for f in state["facts"]:
        groups.setdefault((f["list"], fkey(f)), []).append(f)
    w = {"event": {}, **{L: [] for L in LISTS}}
    superseded = []
    for (L, _k), fs in groups.items():
        fs.sort(key=lambda f: msgs[str(f["msg"])]["ord"])
        best = fs[-1]
        superseded += [(old, best) for old in fs[:-1]]
        if L == "event":
            fld = str(best.get("field", "")).lower()
            w["event"][fld] = str(best.get("value")) if fld == "start_time" else num(best.get("value"))
        else:
            w[L].append(best)
    return w, superseded


# ---------------------------------------------------------------- planning (plain code)
def compute(w):
    e = w["event"]
    P = {"missing": [], "assumptions": [], "warnings": [], "cap_issues": []}
    need = ["students", "team_size", "duration_hours", "budget_total", "judges_confirmed",
            "honorarium", "minutes_per_team", "max_teams_per_judge"]
    P["missing"] = [k for k in need if not isinstance(e.get(k), (int, float))]
    if not P["missing"] and (e["team_size"] <= 0 or e["max_teams_per_judge"] <= 0):
        P["missing"] = ["valid team_size / max_teams_per_judge"]
    if P["missing"]:
        return P

    def cap(t):
        for c in w["constraints"]:
            if str(c.get("type")).lower() == t:
                return num(c.get("value"))

    students = e["students"]
    teams = math.ceil(students / e["team_size"])
    staff = e.get("staff")
    if not isinstance(staff, (int, float)):
        staff = 0
        P["assumptions"].append("No staff number in the messages; assumed 0.")
    needed = math.ceil(teams / e["max_teams_per_judge"])
    conf = int(e["judges_confirmed"])
    used = min(needed, conf)
    tpj = math.ceil(teams / used) if used else 0
    block = tpj * e["minutes_per_team"]
    P["judging"] = {"needed": needed, "confirmed": conf, "used": used, "teams_per_judge": tpj,
                    "minutes_per_team": e["minutes_per_team"], "block_minutes": block,
                    "honorarium": e["honorarium"], "cost": used * e["honorarium"]}
    people = students + staff + used
    P.update(teams=teams, students=students, staff=staff, people=people, start_time=e.get("start_time"))
    P["assumptions"].append("People to feed = students + staff + judges actually needed.")

    # venue: cheapest hall that seats everyone and has every required feature
    feats = [str(c.get("value", "")).lower() for c in w["constraints"]
             if str(c.get("type")).lower() == "venue_feature"]
    cap_v = cap("max_cost_venue")
    cands = []
    for v in w["venues"]:
        cp, pr = num(v.get("capacity")), num(v.get("price"))
        if cp is None or pr is None:
            continue
        text = (" ".join(map(str, v.get("features") or [])) + " " + str(v.get("name", ""))).lower()
        if cp >= people and all(ft in text for ft in feats) and (cap_v is None or pr <= cap_v):
            cands.append((pr, cp, v))
    P["venue"] = None
    if cands:
        pr, cp, v = min(cands, key=lambda t: (t[0], t[1]))
        P["venue"] = {"name": v.get("name"), "capacity": cp, "price": pr, "features": v.get("features") or []}

    spent = [(str(f.get("item")), num(f.get("amount"))) for f in w["spent"] if num(f.get("amount")) is not None]
    spent_total = sum(a for _, a in spent)
    venue_cost = P["venue"]["price"] if P["venue"] else 0
    budget = e["budget_total"]
    reserve = 0
    for c in w["constraints"]:
        t, v = str(c.get("type")).lower(), num(c.get("value"))
        if v is not None and t == "budget_reserve_pct":
            reserve += budget * v / 100
        if v is not None and t == "budget_reserve_amount":
            reserve += v

    # food: prefer the "standard" option, downgrade only if budget or a cap forces it
    opts = sorted([(num(f.get("price_per_head")), str(f.get("item"))) for f in w["food"]
                   if num(f.get("price_per_head")) is not None], reverse=True)
    P["food"] = None
    if opts:
        pref = [o for o in opts if "standard" in o[1].lower()] or opts[:1]
        order = pref + [o for o in opts if o not in pref]
        fixed = spent_total + venue_cost + P["judging"]["cost"]
        cap_f = cap("max_cost_food")
        choice = next(((p, i) for p, i in order if fixed + p * people + reserve <= budget
                       and (cap_f is None or p * people <= cap_f)), None) or min(opts)
        if choice != pref[0]:
            P["assumptions"].append(f"Food downgraded to '{choice[1]}' because '{pref[0][1]}' breaks the budget or a cap.")
        P["food"] = {"item": choice[1], "per_head": choice[0], "qty": people, "total": choice[0] * people}

    lines = list(spent)
    if P["venue"]:
        lines.append(("Venue: " + str(P["venue"]["name"]), venue_cost))
    if P["food"]:
        lines.append((f"Food: {P['food']['qty']} x Rs {P['food']['per_head']:,} ({P['food']['item']})", P["food"]["total"]))
    lines.append((f"Judges: {used} x Rs {e['honorarium']:,}", P["judging"]["cost"]))
    total = sum(a for _, a in lines)
    P["budget"] = {"total": budget, "lines": lines, "spent": spent_total, "cost": total,
                   "remaining": budget - total, "reserve": reserve}
    for t, amt in (("max_cost_food", P["food"]["total"] if P["food"] else 0),
                   ("max_cost_venue", venue_cost), ("max_cost_judging", P["judging"]["cost"])):
        c = cap(t)
        if c is not None and amt > c:
            P["cap_issues"].append(f"{t} is Rs {c:,} but plan needs Rs {amt:,}")
    for c in w["constraints"]:
        if str(c.get("type")).lower() == "other":
            P["warnings"].append("Not machine-checked, please read: " + str(c.get("text") or c.get("value")))

    # schedule
    dur = int(e["duration_hours"] * 60)
    sess = [(str(s.get("name")), num(s.get("minutes"))) for s in w["sessions"] if num(s.get("minutes"))]
    pick = lambda pat: [s for s in sess if re.search(pat, s[0], re.I)]
    opening = pick(r"open|kick|welcome|check-?in|registr")
    lunch = pick(r"lunch|meal|food")
    closing = pick(r"clos|award|ceremon|prize")
    used_names = {s[0] for s in opening + lunch + closing}
    other = [s for s in sess if s[0] not in used_names]
    if not opening:
        opening = [("Kickoff and briefing", DEF_OPENING)]
        P["assumptions"].append(f"No opening session given; assumed {DEF_OPENING} min.")
    if not lunch:
        lunch = [("Lunch", DEF_LUNCH)]
        P["assumptions"].append(f"No lunch length given; assumed {DEF_LUNCH} min.")
    if not closing:
        closing = [("Awards and closing", DEF_CLOSING)]
        P["assumptions"].append(f"No closing session given; assumed {DEF_CLOSING} min.")
    fixed_min = sum(m for _, m in opening + other + lunch + closing) + block
    build = dur - fixed_min
    min_build = cap("min_build_minutes") or DEF_MIN_BUILD
    b1 = max(int(build / 2 / 5) * 5, 0)
    seq = opening + [("Build time (part 1)", b1)] + other + lunch + [("Build time (part 2)", build - b1),
          (f"Judging: each judge visits {tpj} teams x {e['minutes_per_team']} min", block)] + closing
    t, sched = 0, []
    for name, m in seq:
        sched.append({"name": name, "minutes": m, "start": t, "end": t + m})
        t += m
    P["schedule"] = sched
    P["schedule_info"] = {"duration": dur, "build": build, "min_build": min_build, "sum": t}
    return P


def validate(P, w):
    C = []
    add = lambda n, ok, d: C.append({"name": n, "ok": bool(ok), "detail": d})
    names = ["Within budget", "Venue fits", "Schedule valid", "Enough judges", "All areas covered", "Food covers everyone"]
    if P["missing"]:
        add("Correct figures", False, "missing facts: " + ", ".join(P["missing"]))
        for n in names:
            add(n, False, "cannot check, facts missing")
        return C
    J, B = P["judging"], P["budget"]
    add("Correct figures", True, f"{P['teams']} teams; {P['people']} people = {P['students']} students + {P['staff']} staff + {J['used']} judges")
    ok = B["remaining"] >= B["reserve"] and not P["cap_issues"]
    add("Within budget", ok, f"cost Rs {B['cost']:,} of Rs {B['total']:,} (left Rs {B['remaining']:,}, reserve Rs {B['reserve']:,.0f})"
        + ("; " + "; ".join(P["cap_issues"]) if P["cap_issues"] else ""))
    v = P["venue"]
    add("Venue fits", v, f"{v['name']} seats {v['capacity']} for {P['people']} people" if v
        else f"no venue seats {P['people']} people with all required features")
    S = P["schedule_info"]
    sok = S["sum"] == S["duration"] and all(s["minutes"] > 0 for s in P["schedule"]) and S["build"] >= S["min_build"]
    add("Schedule valid", sok, f"blocks add up to {S['sum']} of {S['duration']} min; build time {S['build']} min (min {S['min_build']})")
    add("Enough judges", J["confirmed"] >= J["needed"],
        f"need {J['needed']} ({P['teams']} teams, max per judge), have {J['confirmed']}; each covers {J['teams_per_judge']} teams")
    add("All areas covered", all([P["venue"], P["schedule"], P["food"], P["judging"], P["budget"]]),
        "venue, schedule, food, judging, budget")
    short = [f for f in w["food_orders"] if num(f.get("quantity")) is not None and num(f.get("quantity")) < P["people"]]
    add("Food covers everyone", not short,
        "; ".join(f"order of {num(f['quantity'])} meals is less than {P['people']} people" for f in short)
        or f"{P['people']} meals planned")
    return C


def analyze(state):
    w, sup = build_world(state)
    P = compute(w)
    return w, sup, P, validate(P, w)


def plan_ok(C):
    return all(c["ok"] for c in C)


# ---------------------------------------------------------------- message log
def message_rows(state, sup):
    old_ids = {id(o): b for o, b in sup}
    rows = []
    for n in sorted(state["messages"], key=int):
        m = state["messages"][n]
        fs = [f for f in state["facts"] if str(f["msg"]) == n]
        if n in state["rejected"]:
            st, why = "REJECTED", state["rejected"][n]
        elif not m["relevant"] or not fs:
            st, why = "IGNORED", m["note"] or "no plan fact in this message"
        elif all(id(f) in old_ids for f in fs):
            b = old_ids[id(fs[0])]
            st, why = "OUTDATED", f"replaced by newer message {b['msg']}"
        elif all(f["list"] == "proposals" for f in fs):
            st, why = "NOT APPROVED", "request or quote nobody approved; kept out of the plan"
        else:
            st, why = "USED", ""
        rows.append({"n": n, "sender": m["sender"], "date": m["date"], "gist": m["gist"] or m["text"][:60],
                     "status": st, "why": why})
    return rows


def explain(state, sup, ids):
    for old, best in sup:
        k = f"sup:{old['msg']}:{best['msg']}:{old['list']}:{fkey(old)}"
        if k not in state["noted"]:
            state["noted"].append(k)
            note(state, "OUTDATED", f"Message {old['msg']} said {describe(old)}; newer message {best['msg']} says "
                 f"{describe(best)}. Using the newer one.")
    for r in message_rows(state, sup):
        if r["n"] in map(str, ids) and r["status"] in ("IGNORED", "OUTDATED", "NOT APPROVED"):
            note(state, r["status"], f"Message {r['n']} ({r['sender']}): {r['why']}.")


# ---------------------------------------------------------------- runs
def run_pack(state, raw):
    state["run_start"] = len(state["trace"])
    ex = extract(state, raw, 1)
    ids = add_extraction(state, ex, False, raw)
    _, sup, P, C = analyze(state)
    explain(state, sup, ids)
    note(state, "PLAN", "VALID" if plan_ok(C) else "INVALID: " + "; ".join(c["name"] + ": " + c["detail"] for c in C if not c["ok"]))
    save_state(state)


def run_update(state, raw):
    state["run_start"] = len(state["trace"])
    _, _, oldP, oldC = analyze(state)
    old_ok = plan_ok(oldC)
    snap = copy.deepcopy((state["facts"], state["next_msg"]))
    ex = extract(state, raw, state["next_msg"])
    ids = add_extraction(state, ex, True, raw)
    _, sup, P, C = analyze(state)
    if old_ok and not plan_ok(C):
        reasons = "; ".join(f"{c['name']}: {c['detail']}" for c in C if not c["ok"])
        state["facts"], _ = snap
        for i in ids:
            state["rejected"][str(i)] = reasons
        note(state, "REJECTED", f"Message(s) {', '.join(map(str, ids))} would break the plan, so they were rejected "
             f"and the previous valid plan was kept. Reason: {reasons}")
        _, sup, P, C = analyze(state)
    else:
        explain(state, sup, ids)
        changed = [a for a in AREAS if json.dumps(oldP.get(a), default=str) != json.dumps(P.get(a), default=str)]
        if changed:
            note(state, "UPDATED", "Recomputed from code. Areas changed: " + ", ".join(changed)
                 + ". Areas that made model calls: reading only.")
        else:
            note(state, "UPDATED", "Message read; no area changed. Areas that made model calls: reading only.")
    note(state, "PLAN", "VALID" if plan_ok(C) else "INVALID: " + "; ".join(c["name"] + ": " + c["detail"] for c in C if not c["ok"]))
    save_state(state)
