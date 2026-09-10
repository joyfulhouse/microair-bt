# Micro-Air EasyStart Flex public prior art

Accessed: 2026-09-10  
Scope: public documentation for EasyStart Flex and related EasyStart 364/368/X36/X48/X72 Bluetooth units, their mobile applications, reset/relearn behavior, faults, and community BLE work.  
Method: official Micro-Air material was preferred; store listings were checked directly; community claims are clearly labeled and are not treated as an OEM protocol specification.

## Executive findings

1. **Official material confirms that bad learned data can prevent a successful compressor start.** Micro-Air lists bad learn data as a possible cause of a Stall, and defines Stall as a failed start or loss of motor speed. The Bluetooth manual also provides a Default Ramp diagnostic mode that bypasses learned data to test whether the compressor starts. This supports the project's hypothesis, though the official wording is **bad learn data**, not specifically age-related “staleness.”
2. **Bluetooth relearn is an app setting, followed by physical compressor cycles.** The documented sequence is: connect while EasyStart is powered, enable ReLearn, send settings, power down, then complete five successful starts. Each learning run must operate the compressor for at least 30 seconds; early faults do not count.
3. **There is no documented non-BLE Flex factory-reset fallback.** Micro-Air explicitly warns not to open Bluetooth models. Older non-Bluetooth 364/368 units use an internal JP1 jumper (pins 4–6 for the first learning start, then back to 3–4). Ordinary power cycling can clear lockout faults but does not erase learning.
4. **The public BLE read path is already demonstrated in working ESPHome configurations.** Community code publishes the service and two characteristics, a `ReadLive` command, telemetry offsets, and status enumeration. No published relearn/write command was found in this public prior art.
5. **Published UUIDs are not unique to Micro-Air.** They are the STMicroelectronics sample UART/Chat UUIDs. Discovery should combine GATT data with the official case-sensitive `EasyStart_` name convention.

## Source register and quotations

Quotes are intentionally short; the links point to the complete source text.

### Primary: Micro-Air

| ID | Source | Relevant quotation |
|---|---|---|
| O1 | [EasyStart Flex product page](https://www.microair.net/products/easystart-flex-home-ac-soft-starter) | “adaptive learning and optimization technology” |
| O2 | [EasyStart Bluetooth Diagnostic Manual, rev. 2.1, 2022-06-01](https://www.micro-air.com/support-documents/installation_resources/EasyStart_Bluetooth_Manual.pdf) | “Tap the ‘ReLearn’ switch to green. Tap the ‘Send Settings to EasyStart’ button.” |
| O3 | [Learning and Relearning knowledge-base article](https://www.micro-air.com/kb-easystart/articles_troubleshooting/easystart_Relearning_an_EasyStart_Soft_Starter.htm) | “Relearning is simply restoring EasyStart back to its factory settings, ready to learn again.” |
| O4 | [Flashing Indicator Lights](https://www.micro-air.com/kb-easystart/articles_troubleshooting/easystart_Flashing_Indicator_Lights.htm) | “Bad learn data” |
| O5 | [Solid Indicator Lights](https://www.micro-air.com/kb-easystart/articles_troubleshooting/easystart_Solid_Indicator_Lights.htm) | “Self-Resetting faults will reset automatically and attempt a restart after three minutes.” |
| O6 | [Advanced Troubleshooting Guide, rev. 2.1, 2024-11-20](https://www.micro-air.com/support-documents/installation_resources/EasyStart_Advanced_Troubleshooting.pdf) | “Bad saved data may be erroneously tripping faults after a wiring error is resolved.” |
| O7 | [System is Not Cooling, rev. 1.0, 2025](https://www.micro-air.com/support-documents/installation_resources/EasyStartInitialTroubleshooting.pdf) | “EasyStart’s LEDs should light up and then it starts the compressor after any internal delays” |
| O8 | [Basic EasyStart Troubleshooting](https://www.micro-air.com/kb-easystart/articles_troubleshooting/easystart_Basic_EasyStart_Trouble_Shooting.htm) | “If the lights are off, then the thermostat has most likely stopped the compressor because EasyStart has no power.” |
| O9 | [Home AC Wiring Guide, rev. 1.18, 2025](https://www.micro-air.com/support-documents/residential/current/EasyStart_HomeResidential_Installation_Guide.pdf) | “be sure the compressor has started five times completing the 5 learns” |
| O10 | [Flex Quick Installation Guide, v1.0, 2025](https://micro-air.com/support-documents/EasyStart/EasyStart-Flex-quick-install-insert.pdf) | “Please allow at least 8 cycles to complete before operating on a limited power source.” |
| O11 | [EasyStart 364/368 Installation Manual, rev. 1.06, 2017-01-09](https://www.micro-air.com/support-documents/misc/current/EasyStart_364_368_Installation_Manual_fce0e4cc-954b-473e-a058-f9ef17c0a41e.pdf) | “place a jumper on pins 4 and 6 as shown” |
| O12 | [Relearning EasyStart 364, rev. 1.00](https://www.micro-air.com/support-documents/installation_resources/EasyStart364_Relearning.pdf) | “Factory Default (across pins 3 and 4) Relearn Position (across pins 4 and 6)” |
| O13 | [Relearning EasyStart 368, rev. 1.00](https://www.micro-air.com/support-documents/installation_resources/EasyStart368_Relearning.pdf) | “Relearning EasyStart – 368” |
| O14 | [Bluetooth module overview](https://www.micro-air.com/kb-easystart/article_presales/easystart_What_Is_The_EasyStart_Bluetooth_Module.htm) | “The Bluetooth module does NOT allow you to control your AC unit” |
| O15 | [EasyStart installation knowledge bank](https://www.micro-air.com/kb-easystart/cat_installation.htm) | “Can a Generator Be Used for the 5-Start Learning Process?” |
| O16 | [EasyStart troubleshooting knowledge bank](https://www.micro-air.com/kb-easystart/cat_troubleshooting.htm) | “EasyStart Bluetooth Diagnostics Manual (Available for: X36, X48, X72 and Flex models)” |

### App stores and version indexes

| ID | Source | Relevant quotation |
|---|---|---|
| A1 | [Google Play: EasyStart (`net.microair.easystart`)](https://play.google.com/store/apps/details?id=net.microair.easystart) | “Monitoring, troubleshooting, relearning, and upgrading your Micro-Air EasyStart can now be accomplished via a Bluetooth LE connection” |
| A2 | [Apple App Store: EasyStart (`id1513065167`)](https://apps.apple.com/us/app/easystart/id1513065167) | “App was updated for Apple's new Age Ratings Requirements.” |
| A3 | [Apple lookup API](https://itunes.apple.com/lookup?id=1513065167) | “bundleId”: “net.microair.easystart” |
| A4 | [AppBrain Android metadata](https://www.appbrain.com/app/easystart/net.microair.easystart) | “The latest version available is 4.3.” |
| A5 | [APKPure historical index (secondary)](https://apkpure.net/easystart/net.microair.easystart) | “This update further corrects some screen layout/interference issues introduced in Android 15” |

### Community and implementation evidence

| ID | Source | Relevant quotation |
|---|---|---|
| C1 | [Original Keen-coffee ESPHome file, immutable commit](https://github.com/Keen-coffee/home_assistant/blob/65e820c73ada54b57644e49d579404daee432b84/easyStart) | `service_uuid: "d973f2e0-b19e-11e2-9e96-0800200c9a66"` |
| C2 | [Original Home Assistant Reddit thread](https://www.reddit.com/r/homeassistant/comments/1dm00lg/integration_for_microair_easystart/) | “I reversed the Android APK to get information for how it was doing it.” |
| C3 | [Derek Seaman maintained ESPHome integration](https://github.com/DerekSeaman/ESPHome-Micro-Air-EasyStart) | “based on the original work by Keen-coffee” |
| C4 | [Maintained ESPHome base YAML, immutable commit](https://github.com/DerekSeaman/ESPHome-Micro-Air-EasyStart/blob/5ff263d528046042781236a12fe27c6cd2ab968f/examples/Micro-Air%20EasyStart%20base.yaml) | `value: [0x7B, 0x22, 0x43, 0x6D ... 0x7D]` |
| C5 | [Home Assistant community validation thread](https://community.home-assistant.io/t/micro-air-easystart-flex-esphome-integration/995261) | “it works great” |
| C6 | [Alternating fork/tutorial](https://github.com/Alternating/HA-micro-air-softstart) | “Real-time monitoring of AC unit electrical parameters” |
| C7 | [Alternating issue with observed name](https://github.com/Alternating/HA-micro-air-softstart/issues/1) | “EasyStart_25AC” |
| C8 | [Unpublished native-HA user report](https://www.reddit.com/r/homeassistant/comments/1v9bobb/i_made_custom_integration_for_microair_easystart/) | “connects microair eaststart directly to home assistant without the need for esp32” |
| C9 | [Flex relearning Reddit report](https://www.reddit.com/r/Generator/comments/1evox0b) | “I would do the relearn again.” |
| C10 | [Caravaners Forum unsuccessful inverter/relearn report](https://www.caravanersforum.com/viewtopic.php?t=84108) | “After replacing these capacitors, and following the EasyStart's ‘relearning’ procedure, the same fault continued to persist.” |
| C11 | [Aluminum Camper forum support anecdote](https://aluminumcamperforum.com/index.php?topic=891.0) | “the control board got confused from my first wiring attempt” |
| C12 | [Flex failure/relearn Reddit report](https://www.reddit.com/r/Generator/comments/1m2c23o/microair_easystart_flex_failure_after_1_year_of/) | “Increase the start delay time and relearn.” |
| C13 | [ST BLE stack programming manual](https://www.st.com/content/ccc/resource/technical/document/programming_manual/group0/e7/38/f3/16/a3/b7/4c/e2/DM00698052/files/DM00698052.pdf/jcr%3Acontent/translations/en.DM00698052.pdf) | “TX (notification), RX(write without response)” |

## What learning means

Micro-Air says the algorithm adapts to the connected compressor’s individual startup characteristics so it can optimize current reduction [O1, O3]. The general Bluetooth manual says the first **five successful cycles** populate the learned profile and that the learned data is then retained until a factory reset [O2]. The current Home guide likewise says to complete five starts before alternate power [O9].

The newer Flex quick insert says to allow **at least eight cycles** before limited-power operation [O10]. This is a real document-level difference: five is the stated learned-start count in the diagnostic and Home manuals; eight is the current Flex quick-guide operating recommendation. The most conservative field practice is eight mains cycles, while treating the app’s Learned Starts count of five as completion of the formal learning algorithm.

Official reasons to relearn [O2, O3]:

- compressor run capacitor replaced;
- EasyStart moved to a different motor/A/C;
- power was applied while miswired, wiring was corrected, and faults remain;
- initial learning occurred on a source that was not a good learning environment.

## Official Bluetooth relearn procedure

The complete OEM wording is on page 9 of [the Bluetooth manual][O2]. The verbatim UI instruction is: **“Tap the ‘ReLearn’ switch to green. Tap the ‘Send Settings to EasyStart’ button.”** The complete operational sequence, faithfully transcribed with electrical actions made explicit, is:

1. Use cooling or heat-pump operation consistently through the process. Apply power to EasyStart and connect in the official app.
2. Open **Re-learn**, turn **ReLearn** on/green, and press **Send Settings to EasyStart**. Confirm success; disconnect or close the app.
3. Power the system down. This saved setting makes the **next** power cycle learning start 1.
4. Prefer shore/utility power on a circuit that can normally start the compressor without EasyStart. A generator/inverter is permissible only when necessary; turn generator economy mode off.
5. Restore power and let the **compressor**, not merely the fan, run for at least 30 seconds. Then power down.
6. Repeat the power-up/run/power-down sequence four more times, for **five successful learning starts total**.
7. After the first successful start, natural cycling may complete the remaining starts. A fault within the first 15 seconds discards that attempt and does not increment **Learned Starts**.

Safety/model boundary: this procedure is for Bluetooth models. Micro-Air says Bluetooth and non-Bluetooth procedures are not interchangeable [O3], and warns that opening a Bluetooth model without instruction may void its warranty [O2].

## Non-Bluetooth 364/368 physical relearn

This is the documented hard-reset fallback for legacy **non-Bluetooth** 364/368 boards, not for Flex/Bluetooth [O11–O13]:

1. Remove line power; open the enclosure and expose JP1.
2. Move the shorting jumper from storage/normal pins **3–4** to relearn pins **4–6**.
3. Restore mains power and start the compressor once. The model-specific sheets say to run it for 10 seconds.
4. Remove power immediately after that first start. Return JP1 to **3–4**.
5. Refit the cover/seal, then complete four additional starts. Allow refrigerant pressure to equalize between starts (the installation manual says typically 3–5 minutes).

JP2 on some old boards disables the anti-short-cycle timer if physically cut. It is **not** a reset control and should not be treated as one [O11]. No official EasyStart reset pushbutton or DIP-switch procedure was located. For Flex/Bluetooth, the official public route is the app; if a fault removes normal switched power too quickly to connect, the Bluetooth manual describes temporarily powering the black and white leads from the input side, a task for a qualified person [O2].

An ordinary power cycle clears a non-self-resetting fault lockout; it does **not** erase learned compressor data [O2, O4–O6].

## Consolidated official fault and LED table

Current definitions are from the flashing/solid KB pages and the 2024 advanced guide [O4–O6]. “Self-reset” normally means a retry after approximately three minutes. A lockout requires removing line power.

| State / fault | Bluetooth/flashing LED | Legacy solid LEDs | Current reset behavior | Meaning / prominent causes |
|---|---:|---|---|---|
| Not active | Power LED off | all off, compressor off | N/A | No power to EasyStart; inspect thermostat, breaker, and wiring. |
| Normal | steady green power + steady green normal | all off while compressor runs | N/A | Powered and no active fault. |
| Unexpected Current | 1 red | D23 | Lockout | Large current seen at the beginning of startup; verify wiring, then relearn if appropriate. |
| Over-Current | 2 red | D22 | Self-reset | Measured current exceeded the model’s allowed maximum. |
| Short-Cycle Prevention Timer | 3 green on FRM B27+; 3 red on B26 and earlier | D22 + D23 | Self-reset after timer | Normal prevention of restart before pressure equalizes. |
| Power Interruption | 3 red | D22 + D23 | Self-reset | Line power disappeared for several AC cycles; EasyStart stopped to avoid overload. |
| Open Overload / Klixon | 4 red | D21 | Self-reset | Compressor overload switch opened; possible airflow/water-flow, compressor, or overload-switch problem. |
| Stall | 5 red | D21 + D23 | Self-reset | Start failed or motor failed to reach/maintain speed; causes include supply/wiring voltage collapse, capacitor/compressor failure, miswiring, wrong model, or bad learn data. |
| Wrong Line Voltage | 6 red | D21 + D22 | Lockout | On 120-V-only models, sensed voltage is above roughly 150 V. |
| Miswiring / Start Winding Not Detected | 7 red | D21 + D22 + D23 | Lockout | Orange/black/L2 path does not establish the expected compressor start-winding circuit. |

Flash cadence: half-second on/off pulses within a sequence and one second off between sequences; one repeating flash per second is code 1 [O4, O6]. Fault/status information is also exposed in the app, but Micro-Air says observing LEDs can be better for real-time diagnosis [O4].

**Legacy conflict:** the 2017 364/368 manual reverses part of the modern reset guidance: it describes Over-Current as requiring a power cycle and other faults as three-minute reset cases [O11]. Use the current table for current Flex firmware and the exact model-specific manual for old boards.

## Does a stale learned profile block compressor starts?

### Confirming evidence

- Current official LED documentation lists **bad learn data** among Stall causes [O4, O5]. Stall is the condition where a start failed or the motor stopped/failed to reach the required speed.
- The official Bluetooth manual’s **Use Default Ramp** mode bypasses learned data and is explicitly presented as a diagnostic way to rule out bad learned data or see the compressor start [O2]. This is the strongest causal test described publicly.
- The advanced guide says invalid saved data after miswiring may keep tripping faults after wiring is corrected, and directs the user toward factory relearn [O6].

### Qualification and contrary evidence

- The documentation supports **bad/invalid** learned data; it does not say a correct profile becomes invalid merely because it is old. Calling the condition “stale” is a reasonable project shorthand, not OEM terminology.
- A compressor that makes **no start attempt at all** is more commonly routed by Micro-Air toward no power, control/wiring, or EasyStart hardware diagnosis [O6–O8]. Bad learn data is documented under Stall, where a start is attempted but unsuccessful.
- Community reports show relearn is not a universal cure: one inverter case remained broken after relearn [C10], and a later Flex report describes repeated support-directed relearns without durable resolution [C12]. These are anecdotes, not controlled tests.
- Default Ramp and fault-disable controls are diagnostic settings. The OEM manual says Default Ramp should generally be used only under Micro-Air direction; fault protection should not be disabled without technician direction [O2].

Conclusion: **confirmed as possible, not proven as the cause of every “compressor won’t start” event.** A safe diagnostic ordering is status/LED read → power/wiring/capacitor/source checks → OEM-directed Default Ramp test → relearn when one of the documented reasons applies.

## Mobile applications

### Android

- Official listing: [Google Play][A1]
- Package: `net.microair.easystart`
- Name/developer/category: EasyStart, CseaTec LLC/CSEATEC LLC, Tools
- Current observation: updated **2026-07-22**, 10K+ downloads. Google’s public page did not expose the numeric version.
- Secondary AppBrain metadata reports **4.3**, 3.71 MB, Android 8.1+, and the same 2026-07-22 update date [A4].
- Current Play release note: compliance with the newer minimum Android SDK plus improved Bluetooth scanner filtering during autodetection [A1].
- Partial secondary history at APKPure [A5]: 4.2 (2025-02-24), 3.1 (2024-03-12), 3.0 (2023-09-08), 2.6 (2023-08-24). Treat these historical dates as secondary metadata.

### iOS/iPadOS

- Official listing: [Apple App Store][A2]
- Apple ID: `1513065167`; bundle ID `net.microair.easystart` [A3]
- Seller: CseaTec LLC; free; requires iOS/iPadOS 14.0+
- Current version observed: **4.1**, 2025-12-20.
- Official version history, paraphrased from Apple: 4.1 age-rating update; 4.0 (2025-02-19) latest-iOS/bug/product support; 3.1 (2024-02-05) diagnostic-upload/customer-service improvements; 3.0 (2023-08-27) robustness/product/UX; 2.2 (2022-09-19) screen-change crash fixes; 2.1 (2022-09-17) iOS 16 support; 2.0 (2022-09-12) fixes and three stored EasyStart IDs; 1.21 (2021-08-26) correction to an Update-screen regression; 1.2 (2021-08-24) firmware-update preparation; 1.1 (2021-08-16) clearer Diagnose progress and textual status labels; 1.0 (2020-07-31).

Both official store descriptions cover BLE monitoring, troubleshooting, relearning, diagnostic upload, and device-firmware updating [A1, A2]. The app is diagnostic; it does not replace the thermostat [O14]. The device must be powered, and only one BLE client can connect at a time [O2]. Micro-Air also warns that minor **device firmware** updates may have no public release notes; those are distinct from the mobile-app histories above [O2].

## Published BLE/GATT prior art

### Device discovery

- Official local-name prefix: case-sensitive `EasyStart_`; the manual’s example is `EasyStart_CFFA` [O2].
- Community observations include redacted `EasyStart_XXXX` scan output and `EasyStart_25AC` [C2, C7]. Best-supported pattern: `EasyStart_` plus four uppercase hexadecimal-looking characters. The suffix derivation is unknown.
- One maintained implementation matches any name beginning with `EasyStart` [C3, C4].
- EasyStart often advertises only while it is powered by an active HVAC call. Range is repeatedly reported as short; the maintained project recommends roughly 3–6 ft. Those are community operational observations, though the power requirement is official [O2, C2, C3].

### GATT table

These values occur in the original Keen-coffee code and maintained forks [C1, C3, C4]:

| Role | UUID | Observed operation |
|---|---|---|
| Service | `d973f2e0-b19e-11e2-9e96-0800200c9a66` | Custom UART-like service |
| Device → client | `d973f2e1-b19e-11e2-9e96-0800200c9a66` | notifications / response data |
| Client → device | `d973f2e2-b19e-11e2-9e96-0800200c9a66` | write command |

The community read command written to `…f2e2` is:

```text
7B 22 43 6D 64 22 3A 20 52 65 61 64 4C 69 76 65 7D
```

ASCII: `{"Cmd": ReadLive}` [C1, C4]. It is a 17-byte command; community YAML subscribes to notifications before polling.

Published response decoding [C1, C4]:

| Offset | Community interpretation |
|---:|---|
| byte 2 | status index |
| bytes 4–5, little-endian | live current ÷ 10 A |
| bytes 6–7, little-endian | line frequency = 500000 ÷ raw |
| bytes 8–9, little-endian | last-start peak ÷ 10 A |
| bytes 10–11, little-endian | short-cycle delay |
| bytes 12–13, little-endian | total faults |
| bytes 14–17, little-endian | total starts |

Community status indexes 0–9: Normal, Unexpected Current, Short Cycle Delay, Power Interruption, Stall, Stuck Start Relay, Open Overload, Overcurrent, Bad Wiring, Wrong Voltage [C4]. “Stuck Start Relay” appears in the community/app enumeration but not as a separate row in the current physical LED table.

These UUIDs come from STMicroelectronics’ generic BLE Chat/UART sample: TX/notify `…e1`, RX/write-without-response `…e2` [C13]. Therefore, the service is not a globally unique Micro-Air signature.

### Public implementation status

- Keen-coffee’s original file is public, with the author stating it came from Android APK reverse engineering [C1, C2].
- Derek Seaman’s maintained integration credits that work and targets Flex, with HA-community success reports [C3–C5].
- Alternating’s fork/tutorial adds packaging and dashboard material [C6].
- A user reports a native Home Assistant Bluetooth integration but did not publish its code, so it is testimony rather than inspectable prior art [C8].
- No first-hand public demonstration was found that identifies a 364/368 unit and proves this exact ESPHome GATT implementation against it. Shared behavior across Bluetooth models is plausible from the common OEM app/manual, but remains an inference.

## nRF Connect, captures, and address behavior

A GitHub issue recommends nRF Connect after the official app exposed `EasyStart_25AC` [C7]. However, no public nRF Connect GATT export, Nordic XML/text dump, Wireshark capture, or raw EasyStart advertisement byte dump was found.

One Reddit scan log reports a PUBLIC address and a failed connection at RSSI −87 followed by success after moving closer [C2]. The maintained project author separately reports seeing the broadcasting MAC change after hours [C3]. Those observations are not necessarily compatible; address type/stability should be measured on the target hardware/firmware and not assumed.

## Limitations

- No OEM BLE protocol specification, relearn opcode, authenticated packet trace, nRF export, or raw advertisement payload was found publicly.
- Community telemetry offsets are working-code prior art derived from an APK, not an official specification; validate against the separately decompiled app and live read-only captures.
- The Google Play public page exposes only the current release note and update date. Android version 4.3 and older version history require secondary indexes.
- Community forum reports are anecdotal and sometimes involve different hardware generations, power sources, installation errors, or failed components.
- The requested fully verbatim manuals/procedures are available at the linked OEM PDFs. This report limits reproduction to short excerpts and gives a precise procedural transcription.

## Recommended follow-ups

1. Confirm the GATT triplet, local name, address type, pairing requirement, and `ReadLive` response on the target Flex using a read-only HA/ESPHome BLE capture.
2. Cross-check the public `ReadLive` offsets and status enumeration against the decompiled v4.3 Android app before implementation.
3. Derive and peer-review the app’s exact ReLearn request/reply bytes; do not infer the write from public ESPHome polling code.
4. Treat factory reset/relearn as a confirmed, safety-gated service: require no active cooling call, explicit confirmation, and completion tracking for the required learning cycles.

[O2]: https://www.micro-air.com/support-documents/installation_resources/EasyStart_Bluetooth_Manual.pdf
