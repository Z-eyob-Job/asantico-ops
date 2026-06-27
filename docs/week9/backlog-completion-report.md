# Backlog Completion Report

Project: Asantico Operations Agent
Reporting date: June 26, 2026 (Week 9 checkpoint)
Source of truth: ops-agent/BACKLOG.md and ops-agent/SPEC.md at the submitted commit

## How completion is measured

Completion is counted over the forward backlog in ops-agent/BACKLOG.md: the P0,
P1, and P2 task lists, which together hold 17 tracked items. A task counts as
done only when the code is on main, has a test, and the test passes in CI. This
is a strict definition on purpose: the safety properties of this project mean a
half wired tool that bypasses the gate is worse than no tool, so partial work is
not counted as done.

## Status at this checkpoint

| Tier | Description | Items | Done |
|------|-------------|-------|------|
| P0 | Foundation: spine, policy gate, observability, MCP, CI, uv | 5 | 5 |
| P1 | Core: real CLI wrappers, RAG wiring, Telegram channel, LLM router | 8 | varies (see sprint) |
| P2 | Stretch: email channel, skill packs, heartbeat, WhatsApp | 4 | varies (see sprint) |

Foundation (P0) is fully complete and verified: the gateway, agent loop with per
conversation approval state, the three class approval policy with deny by default,
the working offline CLI channel, the structured observability layer, the MCP
server with the gate enforced, the uv environment, and CI all exist and pass. The
spine is the hard, safety critical part and it is done.

## Week 9 implementation sprint

Week 9 is the implementation sprint. The goal this week is to take completion from
the foundation baseline to at least 80 percent by landing the P1 core items plus
the email channel. The path to the target is concrete and additive: each item
below is wrapping an engine that already exists in asantico-cli or
asantico-copilot, or building one well scoped channel, so the work is integration
rather than new invention.

Sprint scope (each lands on main with a passing test before its box is ticked):

- [x] P1: wrap the real asantico-cli tax engine into compute_tax
- [x] P1: wrap the real ReportLab invoice generator into finalize_invoice
- [ ] P1: wrap the real triage logic into triage_work_order
- [ ] P1: wire the knowledge-rag LlamaIndex pipeline behind knowledge_base
- [ ] P1: implement the Telegram channel end to end
- [ ] P1: per chat approval state keyed by Telegram chat id
- [ ] P1: swap the keyword router for an LLM function calling router
- [ ] P1: tests for every wrapper and the Telegram channel
- [ ] P2: email channel (IMAP poll plus SMTP reply)

When these nine items land, completion is 14 of 17, which is 82 percent and clears
the 80 percent target. The remaining open items are deliberately deferred: skill
packs and the scheduled heartbeat are stretch polish, and WhatsApp is out of scope
for this project because the Business Cloud API onboarding cannot be completed in
the timeframe.

## Critical risks for Week 10 final delivery

These are the items most likely to cost time before the final demo, with the
mitigation already designed into the architecture:

- LLM router misfires and selects the wrong tool. Mitigation is structural: the
  policy gate still stops any gated action regardless of router error, so a
  misfire is a wrong answer, never an unapproved send. Router tests reduce the
  frequency.
- Telegram channel is the only item that is genuinely new code rather than a
  wrapper, so it carries the most schedule risk. Mitigation is to build it behind
  the existing channel base interface so it cannot affect the agent or policy, and
  to keep email as a fallback channel for the demo if Telegram verification stalls.
- Retrieval quality on the real backend. The offline backend hits 0.900 hit rate
  and 0.850 MRR with one failing query (Q7). Moving to a stronger embedding backend
  in production should hold or improve this; the eval set and harness already exist
  to verify it after the swap.

## Keeping this report honest as the sprint lands

This report is a living document. As each sprint item lands on main with a passing
test, tick its box above and update the status table and the percentage. Do not
tick a box for code that is not on main or whose test is not passing in CI. The
submitted version of this report should reflect the true state of the repository
at submission time.
