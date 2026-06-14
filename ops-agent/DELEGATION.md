# Delegation Plan: Five Lanes for the Asantico Operations Agent

The skeleton in this repo (gateway, loop, policy, CLI channel, knowledge_base,
tool interfaces, tests) was built and verified by Claude. The next phase turns the stubs
into the real product across five lanes. The lane discipline matches what worked
on prior projects; the single rule is that only Cursor and Codex write source, never
the same file in the same iteration, and nothing merges without an Eyob review.

## Lane 1 - Claude Code (read-only inventory and audit)

Maps both repos (this one and asantico-cli), lists the public functions in the
real tax, PDF, and triage modules so the tool wrappers call the right signatures,
and reports the test status before each iteration. Never edits. Output to
`docs/inventory_weekN.md`.

## Lane 2 - Cursor (primary implementation)

Phase 2 first: replace the tool stubs in `src/tools/domain.py` with real calls
into asantico-cli (tax engine, ReportLab invoice/estimate, triage agent). Then
Phase 3: implement the Telegram channel with python-telegram-bot, then email.
Then Phase 4: the LLM function-calling router. One feature branch at a time.

## Lane 3 - Codex (tests and independent cross-check)

Writes tests for every tool wrapper and channel Cursor builds, and independently
re-implements the tax total so the two can be diffed against the same fixtures
(money math gets two sets of eyes). Owns `tests/`. A Cursor-versus-Codex
disagreement halts the merge until Claude adjudicates.

## Lane 4 - Claude (planning, verification, written artifacts)

Keeps SPEC, README, and the architecture diagram current, runs the safety test
suite after every change, reviews each pull request for grounding and for any new
tool that skipped policy registration, and adjudicates disagreements. Wires the
real LlamaIndex knowledge_base from the knowledge-rag subsystem.

## Lane 5 - Eyob (decisions, keys, channels, merges)

Creates the Telegram bot via BotFather and holds the token in `.env`, sets up the
email app password, decides the autonomy level, curates the knowledge corpus
(policies, tax rules, workflows), runs the live demo, reviews every pull request,
and merges. Final say on everything.

## Handoff order for one build iteration

1. Eyob confirms the iteration scope and provides any keys the iteration needs.
2. Claude Code posts the inventory of the real asantico-cli functions in scope.
3. Claude updates SPEC and the tickets.
4. Cursor implements the assigned wrappers or channel on a branch.
5. Codex writes the tests and the money-math cross-check.
6. Claude runs the safety suite and reviews the PR.
7. Eyob reviews and merges.

## What is already done (do not redo)

The gateway, agent loop, per-conversation approval state, the policy risk model,
the working CLI channel, the knowledge_base retrieval tool, all tool interfaces,
and eight passing tests covering the approval gate, routing, and tax math. The next
phase fills in real tools and real channels behind interfaces that already work.
