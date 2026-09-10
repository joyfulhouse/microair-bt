# Debate synthesis — `microair_bt` v1 specification (round 1, independent mode)

Subject: `wiki/integration-plan.md` at `b895a575bf717dade21feba4a49b70b117fea456`
Contract / plan sha256: `59f75f5bb32786a70842b0887ec801070cefd6796607cce198eb27e1926fcd58`
Seats: `debate-spec-openai` (codex / gpt-6-astra @xhigh, observed), `debate-spec-anthropic`
(claude_code / claude-fable-5-1[1m] @xhigh, observed), `debate-spec-xai` (grok, host default grok-4.6).
Verdicts: **REVISE × 3**. All three endorse the approach (local BLE, three-command structural
whitelist, service-only confirm-gated relearn, connect-on-demand/disconnect-after-poll, no button,
fogmachine layout) and all three say the written spec is not implementer-ready.
Synthesized by pollux; this is advice to the plan gate, not approval. Revised spec: `wiki/integration-plan.md` v1.1.

## Consensus (adopted in v1.1)

| Topic | Seats | Adopted change |
|---|---|---|
| Completion detection rejects `Success\r\n` | xai-3, openai-3, anth-4 | Strip trailing CR/LF/NUL/whitespace, then ≤64 B, bytes 0x20–0x7E, substring; both tokens ⇒ reject; labelled provisional; log verbatim first envelope |
| Bind identity before any `SMask` | xai-4, openai-2, anth-11 | Name `EasyStart_*` + ST GATT triplet + fresh EEPROM model in the control allow-list (`398ULBT` for v1) + write-site regex assertion |
| Bound incoming data | openai-2, anth-11 | Caps: ReadLive 64 B, ReadEEP 1100 B, reject overflow; drop binary during a mask write |
| Transaction-wide lock, connection generation, disconnect on timeout/Fail | openai-4, anth-14 | One per-device lock across connect→command(s)→publish→disconnect; late notifications cannot resolve the next command |
| Read-back must equal the requested mask; distinct outcomes | openai-5, anth-1 | VERIFIED / APPLIED_UNVERIFIED / FAILED; "already in mode" no-write; no auto-retry; 10-min rate limit (`allow_repeat`) |
| Reject masks with SuperLearn/unknown upper bits | openai-1, anth-11 | Refuse service when fresh mask & 0xF0 ≠ 0 (OEM guidance needed) |
| Running guard is a sampled safeguard, trips on typical installs | xai-2, openai-9, anth-3 | Keep default refusal; SCPT-window check (`scpt_delay_s ≥ 10`); stale/missing current refuses even with `allow_running`; error text explains; `allow_running` = OEM-app behaviour |
| Persist request/progress across power cycles and restarts | xai-6, openai-7, anth-1 | Persist mode/requested_at/mask_before/mask_requested/outcome/learned_starts_before on the entry; `learned_starts` raw with sample timestamp; no completion claim in v1 |
| OEM-app coexistence | all | Classify GATT-busy vs no-advertisement; `switch.polling` to pause before OEM sessions/firmware updates; ReadLive-first with short timeout; never evict/queue |
| Availability precisely defined; fail fast; no backoff | openai-8, anth-6 | Unavailable until first valid sample; keep last sample on failures 1–2; unavailable at 3; fixed 60 s; fail fast without `BLEDevice`; `max_attempts` 2 poll / 4 service |
| Unknown status handling | openai-10, anth-13 | Enum option `unknown` + `raw_state` attr; fault = {1,3,4,5,6,7,8,9}, None for unknown |
| Default Ramp | xai-5, openai-11, anth-8 | Bit 1 exposed read-only (all); *write* — see dissent |
| Scope split | openai-11, anth-9 (xai: one PR with control gated) | **PR-1** protocol lib + client + probe + tests (no HA); **PR-2** HA component after probe evidence |
| Full OEM procedure text | openai-9, anth-15 | Utility power, one HVAC mode, ≥30 s compressor per start, 15 s early-fault discard, 5 starts, Flex ≥8 cycles, close app, power down; never automate power cycling |
| MTU | anth-10 | Do not request; log `mtu_size`; MTU-agnostic reassembly (20-byte-chunk test) |
| Probe redaction | anth-16 | Redact non-candidate addresses |
| `powered` sensor from advertisement presence | anth-7 | Added (`binary_sensor.powered`, `last_seen`) — cheapest answer to "is it even powered when the thermostat calls?" |

## Dissent (recorded, not erased)

1. **Cancel / Default-Ramp write.** OpenAI-6: remove `cancel_relearn` (undocumented semantics). Grok-9/anth-12:
   keep with same gates, restore `mask_before`. Anthropic-8: replace both services with one gated
   `set_startup_mode {normal|relearn|default_ramp}` mirroring the app's three switches; OpenAI-11/Grok-5 keep
   Default Ramp *write* out of v1. **Pollux recommendation:** adopt the single `set_startup_mode` service —
   one gate, one verify path, fewer services (ponytail) — with `default_ramp` as an admitted mode because it is
   the OEM's own diagnostic for this exact hypothesis and is reversible; `normal` restores `mask_before` when
   the last request was ours, else `m & 0x1C`. *Human decides whether `default_ramp` ships in PR-2 or is deferred.*
2. **Address identity.** Anthropic-5: unique_id = local name, address mutable and refreshed on discovery.
   OpenAI-11: never automatic same-name rebinding; explicit user-confirmed reconfiguration. **Recommendation:**
   name-keyed unique_id with address refresh via `_abort_if_unique_id_configured(updates=…)` — the link is
   unauthenticated either way, so same-name rebinding adds no surface beyond the address itself.
3. **ReadLive timeout.** Grok-7 ≥15 s; Anthropic-2 5 s on polls to minimise slot hold. **Recommendation:** 10 s
   on polls, 20 s in the service, both provisional until proxy traces exist.
4. **Control allow-list.** OpenAI: exact `398ULBT` only. Anthropic: four known models. **Recommendation:**
   a single constant `CONTROL_MODELS = {"398ULBT"}` in v1; widening is a one-line follow-up after evidence.

## Evidence that would change the synthesis
Read-only probe output (completion envelope, write type, bonding, MTU, address type); a supervised
lifecycle observation after the first live `SMask=01` (self-clear? `learned_starts` reset?); a live Stall +
Default-Ramp start. §11 of the spec now separates probe-resolvable items from supervised-write items.
