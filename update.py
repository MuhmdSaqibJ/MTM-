"""python update.py "new message text"   (continues from the saved state.json)"""
import sys, time
import core, render

core.load_env()
if len(sys.argv) < 2:
    raise SystemExit('Usage: python update.py "new message"')
state = core.load_state()
t0 = time.time()
core.run_update(state, " ".join(sys.argv[1:]))
render.emit(state)
print(f"\nUpdate took {time.time() - t0:.1f}s.")
