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
