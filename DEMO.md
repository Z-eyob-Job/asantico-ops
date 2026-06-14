# Prototype Demo Evidence

End-to-end prototype slice: a user message comes in over a channel, the agent
routes it, runs the right tool, and gates any client/money action behind approval.

## Reproduce the demo

```
cd ops-agent
python -m src.gateway        # CLI channel, no keys
```

Then paste these messages:

```
What is the sales tax rate and how should invoices be addressed?
VEER LOFTS unit 208 has a water leak under the sink
create an estimate for VEER LOFTS unit 208 for $420
draft a message to Saniya
send an update to Saniya       # -> the agent STOPS and asks for approval
approve                         # -> only now is it sent
```

## What the run proves

Routing: a question goes to the grounded knowledge base; a leak becomes an
emergency triage; an estimate is priced with 10.55% tax; a send is gated.

HITL: the `send` produced an `approval_requested` event and did nothing until the
operator replied `approve`, which produced `approval_granted` then `tool_executed`.

Observability: every step is one structured log line with a trace id. The captured
run is in `ops-agent/logs/agent.jsonl` (18 events). Example sequence for the gated
flow (trace ids abbreviated):

```
bd40...  message_received    send an update to Saniya
bd40...  routed              send_client_message (risk=gated)
bd40...  approval_requested  send_client_message
b206...  message_received    approve
b206...  approval_granted    send_client_message
b206...  tool_executed       send_client_message
```

## Evidence checklist for submission

- [x] Logs: `ops-agent/logs/agent.jsonl` (committed)
- [ ] Screen recording of the CLI session above (record locally, attach to the checkpoint)
- [ ] Screenshot of the CI run passing on GitHub (after first push)
- [ ] Screenshot of the MCP Inspector listing the tools (optional, strong evidence)
