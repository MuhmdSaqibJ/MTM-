"""One command:  python plan.py [messages file]   (default: messages.txt)
Runs the full pack, then waits for new messages and updates the plan."""
import os, sys, time, webbrowser
import core, render

core.load_env()
path = sys.argv[1] if len(sys.argv) > 1 else "messages.txt"
raw = open(path, encoding="utf-8").read()
t0 = time.time()
state = core.new_state()
core.run_pack(state, raw)
render.emit(state)
print(f"\nFull run took {time.time() - t0:.1f}s. Interface: report.html | saved trace and plan: output.txt")
try:
    webbrowser.open("file://" + os.path.abspath("report.html"))
except Exception:
    pass
while True:
    try:
        msg = input("\nNew message (empty line to quit): ").strip()
    except EOFError:
        break
    if not msg:
        break
    t0 = time.time()
    core.run_update(state, msg)
    render.emit(state)
    print(f"\nUpdate took {time.time() - t0:.1f}s.")
