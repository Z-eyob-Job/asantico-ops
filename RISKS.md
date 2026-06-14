# Risk Register

Severity x likelihood drives priority. Each risk has an owner and a concrete
mitigation action planned for the next iteration.

| ID | Risk | Severity | Likelihood | Mitigation (next iteration) | Owner |
|----|------|----------|------------|------------------------------|-------|
| R1 | LLM router calls the wrong tool once it replaces keyword routing | High | Medium | Policy gate still stops any gated misfire; add router unit tests with adversarial phrasings; log every routing decision for audit | Project lead |
| R2 | Agent sends a wrong message or invoice to a real client | High | Low | Mandatory approval gate on all sends/finalizations (enforced in policy.py and at the MCP boundary); covered by tests | Project lead |
| R3 | Tenant data leaks onto a document or off the machine | High | Low | Local-first; no-tenant-name rule enforced in the tool layer; EXIF stripped from photos; no client data in logs beyond IDs | Project lead |
| R4 | Real asantico-cli wrappers drift from the engine's actual behavior | Medium | Medium | An independent tax cross-check is added; wrappers covered by tests against real fixtures before merge | Project lead |
| R5 | Telegram process dies and the operator does not notice | Medium | Medium | Run under a process supervisor; add a heartbeat log; alert on missing heartbeat | Project lead |
| R6 | Secrets (API keys, bot token) committed or leaked | High | Low | .env gitignored; CI has no secrets in logs; move to OS keychain / secret manager before production | Project lead |
| R7 | Knowledge base goes stale as policies change | Medium | Medium | Re-index on a schedule; answers cite source files so staleness is visible | Project lead |
| R8 | Approval fatigue leads the operator to rubber-stamp | Medium | Medium | Keep approval prompts specific and few; batch low-risk drafts; never auto-approve | Project lead |

## Next-iteration mitigation actions (committed)

1. Add adversarial router tests and ship the LLM router behind the unchanged gate (R1).
2. Add the independent tax-math cross-check against real fixtures (R4).
3. Run the agent under a supervisor with a heartbeat log and missing-heartbeat alert (R5).
4. Move secrets out of .env into the OS keychain; document the procedure (R6).
5. Add a scheduled knowledge-base re-index job (R7).
