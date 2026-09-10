# Debate (xAI) — microair_bt v1 spec

**Position: REVISE.** Approach is sound (local BLE, 3-command whitelist, service-only relearn + `confirm: true`, connect-on-demand, no firmware/`FMask`/`SCPT`, fogmachine layout). Not implementer-ready: OEM-app coexistence, powered-only vs running-current window, completion matching, and ST-sample write containment need spec text before any live `SMask`.

**Strongest objection:** ship the HA shell against fakes and treat ⚠️ as probe homework; whitelist + no-button already beat the OEM app. Still not APPROVE: live relearn can time out, refuse the only powered window, or collide with an open phone app.

**Would change to APPROVE:** probe of this Flex (completion text including CR/LF, write type, no pairing, powered-idle current) plus spec edits for occupancy vs unpowered, SCPT window, model allow-list, persisted relearn progress. Live Stall + Default-Ramp start would justify omitting Default Ramp *write* without a diagnostic hedge.

## Numbered items

1. **Safety.** Service-only, confirm, no button, verify-after-write, OEM procedure notification: more gated than the app (`Relearn.java:250-262`). `cancel_relearn` is justified (`integration-plan.md:160-162,211`). `current_a ≥ 1.0` is not in the decompile and fights powered-only-while-calling (`device-easystart-flex.md:23-24`); `allow_running` fights `CLAUDE.md:50-51`. Not over-engineered; wrong default window (D-xai-2).

2. **Protocol.** `ReadEEP`/`ReadLive`/`SMask=HH`, `relearn_mask=(m&0x1C)|0x01`, no str/bytes path match `ble-protocol.md:72-79`, `Relearn.java:379-431`. Flaw: “all printable” (`integration-plan.md:81-84`) drops `Success\r\n` (`str.isprintable()` is false for CR/LF); exact text unknown (`ble-transport.md:88-89`) (D-xai-3). Bits 5–7 drop is OEM-faithful.

3. **Connection.** Connect-on-demand is correct (single client; a held link blocks the OEM app and dies on power-down). 60 s is enough to track learning, not starts. 3-failure unavailable is right when idle, wrong if it hides relearn across five power cycles (D-xai-6). Distinguish GATT-busy vs no-ADV (D-xai-1). ReadLive 5 s is the OEM *period*, not proxy RTT (D-xai-7).

4. **Entities.** Live map matches `available-data.md:12-25`. Bit-0 `relearn_pending` is right (⚠️ self-clear). Fault ≠ `{Normal, Short Cycle Delay}` (code 2 is SCPT). Missing: read-only Default-Ramp bit 1. `learned_starts` is the only progress signal.

5. **Scope.** One PR (protocol + HA + read-only probe + tests) is right if first real `SMask` waits on probe ⚠️ 1–4. Do not send update-family/`FMask`/`SCPT`/raw `f2e2`, add a button, pairing, or cloud (D-xai-10).

6. **Goal gaps.** OEM bad-learn test is Default Ramp (`device-easystart-flex.md:47-53`), under Stall, not “no attempt”. Keep it out of the write whitelist; expose bit 1 read-only (D-xai-5, D-xai-8). Unfavourable ⚠️: pairing, MAC rotation, non-printable completion, unit never heard (`ha-proxy-coverage.md:17-19`). Hedge: probe first; persist address+name; strip CR/LF.

7. **Contradictions.** Non-goal “user closes the app” (`integration-plan.md:30`) vs OEM “close the app” (`device-easystart-flex.md:39`). Five starts vs Flex ≥8 cycles (`device-easystart-flex.md:29-32`). `allow_running` vs `CLAUDE.md:50-51`. `relearn_mask` keeps SuperLearn; document, not factory reset (D-xai-9).

## Missed perspectives

**zombie-integrations.** The phone app never yields GATT (`device-easystart-flex.md:22`; `Status.java:48-74` holds while Status is open). If not closed: HA connect-on-demand fails; three polls → unavailable, looks like idle; tracking never runs. Do not kick that client. Coexist: disconnect after each poll (already specified), classify occupied vs unpowered, tell the user to close the app before relearn and during the five starts.

**supply-chain-partner.** `d973f2e0/e1/e2` are ST Chat/UART sample UUIDs (`search-easystart-prior-art.md:210`). Spec correctly refuses UUID-only discovery (`integration-plan.md:169-171`). Bytes remain unauthenticated (`ble-protocol.md:26`, `ble-transport.md:20-22`). Contain at whitelist + post-connect bind: `EasyStart_` name, ST triplet, EEPROM model in `{364ULBT,368ULBT,398ULBT,399BT}` before `SMask`, arg `0..0x1F`, never raw writes. A spoofed `398ULBT` dump can still take a mask write; do not widen the whitelist.

Advice to the plan gate, not approval.

---

## Findings (evidence)

| ID | Sev | Path:line | Problem | Fix |
|---|---|---|---|---|
| D-xai-1 | HIGH | wiki/integration-plan.md:30 | OEM app is a permanent co-client; occupancy looks like idle | Classify busy vs no-ADV; notify close-app; never hold/kick |
| D-xai-2 | HIGH | wiki/integration-plan.md:148 | 1.0 A guard vs powered-only HVAC; allow_running vs CLAUDE.md:50 | Spec SCPT/zero-current window; allow_running ⚠️ post-probe only |
| D-xai-3 | HIGH | wiki/integration-plan.md:81 | All-printable drops CR/LF completions | Strip CR/LF/NUL then require printable + Success/Fail |
| D-xai-4 | HIGH | wiki/integration-plan.md:168 | ST UUIDs; “known model” unspecified; manual address | Allow-list models; bind name+GATT+model before SMask |
| D-xai-5 | MEDIUM | wiki/integration-plan.md:27 | Default Ramp is OEM bad-learn test; v1 writes none | Read-only bit 1; README diagnostic order |
| D-xai-6 | MEDIUM | wiki/integration-plan.md:112 | 3 failures hide relearn across power cycles | Persist progress on entry; hold last state |
| D-xai-7 | MEDIUM | wiki/integration-plan.md:100 | ReadLive 5 s is poll period, not proxy RTT | Timeout ≥15 s until probe |
| D-xai-8 | MEDIUM | wiki/integration-plan.md:156 | 5 vs 8 cycles; Stall vs no-start | Notification + status hedge |
| D-xai-9 | LOW | wiki/integration-plan.md:77 | SuperLearn keep; `normal_mask` ≠ (mask&7)==0 | Document switch-ON math; keep cancel |
| D-xai-10 | MEDIUM | wiki/integration-plan.md:53 | One PR OK; live SMask before probe is not | Gate first write on probe ⚠️ 1–4 |

Verified: two APK reads agree on 24 commands, mask math, offsets, GATT UUIDs; unit not heard 2026-09-10. Inference: 1.0 A threshold, completion CR/LF, GATT-busy error shape, firmware bit-0 self-clear.

Coverage: wiki/integration-plan.md (full), ble-protocol.md, ble-transport.md, available-data.md, device-easystart-flex.md, ha-proxy-coverage.md, CLAUDE.md, four research reports (not debate-spec-*), Relearn.java:250-457, Status.java:48-119, fogmachine coordinator/manifest/protocol. No other seats’ debate files. No BLE/network. No git write.
