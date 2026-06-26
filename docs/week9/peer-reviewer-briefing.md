# Peer Review Briefing (hand this to your reviewer)

Thanks for reviewing my project. It should take about 15 minutes. I am looking
for honest, concrete feedback, not a pat on the back.

## What the project is

Asantico Operations Agent: a local assistant for a property maintenance business.
You message it in plain language and it answers policy questions, triages repairs,
prices estimates and invoices with the right tax, and drafts client messages. The
key safety idea: it pauses and asks for human approval before it ever sends a
message to a client or finalizes anything involving money.

Repo: https://github.com/Z-eyob-Job/asantico-ops (branch: week9-checkpoint)

## What to look at (pick what you have time for)

1. The README and docs/week9/technical-report-draft.md for the big picture.
2. ops-agent/src/policy.py and ops-agent/src/agent/loop.py: the approval gate and
   the agent loop. This is the safety core.
3. ops-agent/src/agent/router.py: how a message gets turned into a tool call.
4. The tests in ops-agent/tests/ and whether they cover what matters.

## If you want to run it (optional, 2 minutes, no keys)

```
git clone https://github.com/Z-eyob-Job/asantico-ops.git
cd asantico-ops/ops-agent
python3 -m pytest tests/ -q
python3 -m src.gateway
```

Then type things like: a tax question, "VEER LOFTS unit 208 has a leak", "create
an estimate for unit 208 for $420", "send an update to Saniya" (watch it stop and
ask for approval).

## What I actually want from you

Give me 2 to 4 concrete comments. For each, tell me roughly how serious you think
it is. The useful kinds of feedback:

- Anything about the safety gate that looks bypassable or fragile.
- Code that is confusing, brittle, or would break on a real input.
- A test that is missing for something important.
- Architecture or naming that does not make sense to you.

Please do not just say "looks good." Even small nits help. You can write them in a
message, a doc, or as GitHub comments, whatever is easiest. Thank you.
