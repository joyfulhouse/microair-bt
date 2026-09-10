# Sources registry (raw, immutable evidence)

Purpose: index of the raw inputs the wiki is distilled from. Never edit files
under `/sources/`; add new evidence and record it here. See [SCHEMA](SCHEMA.md).

| Source | Path | What it provides |
|---|---|---|
| APK (EasyStart, `net.microair.easystart`) | `sources/apk/net.microair.easystart.apk` | The app binary, 3.9 MB. Pulled via `apkeep` 2026-09-10. Git-ignored; regenerate with `apkeep -a net.microair.easystart sources/apk/`. |
| jadx decompile | `sources/decompiled/jadx/` | Java sources; app code under `sources/net/microair/easystart/`. Git-ignored; regenerate with `jadx -d sources/decompiled/jadx sources/apk/net.microair.easystart.apk`. |
| apktool decode | `sources/decompiled/apktool/` | `AndroidManifest.xml`, resources, smali. Git-ignored; regenerate with `apktool d -o sources/decompiled/apktool sources/apk/net.microair.easystart.apk`. |

## Provenance / notes

- APK from a public mirror via `apkeep`. No native libraries; plain Java/Kotlin
  app (no Flutter / React Native bundle).
| Independent APK protocol read — OpenAI lens | `docs/claude/research/explore-apk-protocol-openai.md` (+ `.pollux/reports/…json`, git-ignored) | gpt-6-astra @xhigh, 2026-09-10: full 24-command inventory, GATT, framing, telemetry offsets, update-path exclusion list; 192 citations checked. Feeds [ble-protocol](ble-protocol.md), [ble-transport](ble-transport.md), [available-data](available-data.md). |
| Independent APK protocol read — Anthropic lens | `docs/claude/research/explore-apk-protocol-anthropic.md` | claude-fable-5-1 @high, 2026-09-10: same scope, relearn/faults emphasis; agrees with the OpenAI lens on every byte. |
| HA passive BLE scan near Kaelyn's bedroom | `docs/claude/research/explore-ha-ble-scan.md`, `ble-scan-dump.json` | 2026-09-10, 90 s + 180 s windows over the HA websocket: unit **not heard** on any proxy. Feeds [ha-proxy-coverage](ha-proxy-coverage.md). |
| Public prior art (OEM manuals, app stores, community ESPHome) | `docs/claude/research/search-easystart-prior-art.md` | 2026-09-10: official relearn procedure (power-down + 5 starts), fault/LED table, community `ReadLive` ESPHome configs, observed name `EasyStart_25AC`, ST UART-profile UUID origin. Feeds [device-easystart-flex](device-easystart-flex.md). |
