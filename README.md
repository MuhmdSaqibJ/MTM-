# MTM-
# Mind to Machine: event planner agent

**Idea:** the model only *reads* messy messages (area `reading`). Plain Python does all arithmetic,
planning, validation, supersession and rollback. That keeps tokens low and every part explainable.

## Run
```
cp .env.example .env        # then put your key in .env  (GEMINI_API_KEY=...)
python plan.py messages.txt # full run, then it waits for new messages
python update.py "Finance here. The printing bill came in at Rs 15,000"   # alternative: update from saved state
```
No packages to install (standard library only). Open `report.html` for the interface; `output.txt` holds the final plan and full trace.

## Parts and why they exist
| Part | Job | Without it |
|---|---|---|
| `extract` (1 model call) | turn English / Roman Urdu text into structured facts | we would have to type facts into code |
| `build_world` | newest message wins for the same fact (out-of-date handling) | old caterer price would be used |
| `compute` | venue, schedule, food, judging, budget by arithmetic | wasted tokens and wrong sums |
| `validate` | checks: figures, budget, venue, schedule, judges, areas, food covers everyone | invalid plans accepted |
| `run_update` | apply new message, re-validate, **reject and roll back** if it breaks the plan | wrong messages corrupt the plan |
| `render` | plan, checks, message status and trace | nothing to show judges |

## Design decisions
- Only `reading` calls the model. Updates make 1 call and recompute only what changed (diff printed in the trace).
- A message is rejected when the plan with it applied fails any check; the failed check is the printed reason.
- Unknown constraint kinds: common ones are enforced (`venue_feature`, reserves, cost caps, min build time);
  anything else is shown as a WARNING instead of being silently dropped.
- Schedule defaults (opening 10, lunch 30, closing 15, min build 60) apply only when no message sets them, and are printed as assumptions.

