# Task Backlog: Asantico Operations Agent

Priority order is P0 (gate-blocking) before P1 (core) before P2 (stretch). This is
a solo build, sequenced in phases.

## P0 - Foundation (done)

- [x] Freeze the project scope and architecture (SPEC.md, architecture diagram)
- [x] Decide channels: CLI + Telegram + email; WhatsApp deferred
- [x] Build the runnable spine: gateway, agent loop, policy gate, CLI channel
- [x] Define the tool interface contract the real CLI will implement
- [x] Lock the safety model: gated actions, approval state, deny unregistered tools

## P1 - Core implementation

- [x] Phase 2: wrap real asantico-cli tax engine into compute_tax (with offline fallback; tests pass both ways)
- [x] Phase 2: wrap real ReportLab invoice generator into finalize_invoice (real PDF; offline fallback)
- [ ] Phase 2: wrap the real triage agent into triage_work_order
- [ ] Phase 2: wire the knowledge-rag LlamaIndex pipeline behind knowledge_base
- [ ] Phase 3: implement the Telegram channel end to end
- [ ] Phase 3: per-chat approval state keyed by Telegram chat_id
- [ ] Phase 4: swap the keyword router for an LLM function-calling router
- [ ] Tests for every wrapper and the Telegram channel

## P2 - Stretch

- [ ] Email channel (IMAP poll + SMTP reply)
- [ ] Skills as SKILL.md workflow packs (monthly invoicing run, intake, quarter close)
- [ ] Scheduled heartbeat (proactive reminders for pending approvals)
- [ ] WhatsApp via Business Cloud API (deferred; only if time and verification allow)

## Done (foundation)

- [x] Gateway, agent loop, per-conversation approval state
- [x] Policy risk model with reads/drafts free and sends/finalizations gated
- [x] Working CLI channel (offline, no keys)
- [x] knowledge_base retrieval tool grounded on Asantico policies
- [x] All tool interfaces stubbed and callable
- [x] Eight passing tests: approval gate, routing, tax math, policy denial
