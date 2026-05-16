# System Settings

## What It Does

Global configuration management for the application. Stores key-value settings that control FFmpeg paths, CPU behavior, scan intervals, Jellyfin connection, and other system-wide parameters.

## Success Criteria

1. FFmpeg and FFprobe executable paths are configurable with a test button that validates the binary exists and runs.
2. CPU thread limit (1-32) controls how many threads FFmpeg uses for transcoding.
3. CPU affinity settings (temperature threshold, monitoring interval, cooling wait) control thermal throttling behavior.
4. Continuous scan interval is configurable (controls how often background scanning runs).
5. Excluded directories can be added and removed (directories to skip during scanning).
6. Jellyfin connection settings (host, SSH port, user, key path, API port, API key) are configurable.
7. TranscodeOutputMode (InPlace or Staging) controls where transcoded files are written.
8. **[SUPERSEDED 2026-05-16]** The legacy `SystemSettings.QualityTestEnabled` global row was deleted by the post-transcode disposition migration (`Scripts/SQLScripts/AddPostTranscodeDisposition.py`); the equivalent operator control now lives on `PostTranscodeGateConfig.QualityTestEnabled` and is owned by `post-transcode-disposition.feature.md` criterion 26. This criterion remains here only as a redirect.
9. All settings persist to the SystemSettings table as key-value pairs.
10. The /settings page provides the UI for all configuration.
11. [BUG] The SystemSettings table is properly normalized: (a) `SettingKey` carries a `UNIQUE` constraint and the table contains exactly one row per key (currently has duplicates: `ContinuousScanEnabled`x2, `ContinuousScanIntervalMinutes`x2, `ExcludedDirectories`x4); (b) `DataType` values are case-consistent and constrained to a defined enum (currently mixes `BOOLEAN` / `boolean` / `string` / `INTEGER` / `integer` / `text`); (c) list-shaped values (`AllowedExtensions`, `ExcludedDirectories`) live in dedicated child tables instead of as comma-separated text; (d) per-file overrides (`CRFOverride_<path>` rows) live in a typed override table keyed by `MediaFileId`, not as `SystemSettings` rows with the path mangled into the key. Fixed = a fresh dump of `SystemSettings` shows no duplicate keys, no comma-separated list values, and no `CRFOverride_*` keys.
12. [BUG] The /settings page renders every row in `SystemSettings` somehow -- either via a dedicated UI control for known keys, or via the generic "All System Settings" advanced table for the rest. Fixed = no SystemSettings row exists in the DB without a corresponding visible row on /settings.

## Status

IN PROGRESS

## Scope

```
Features/SystemSettings/**
```

## Files

| File | Role |
|------|------|
| Features/SystemSettings/SystemSettingsController.py | Flask Blueprint -- settings endpoints |
| Features/SystemSettings/SystemSettingsRepository.py | SystemSettings table queries |
| Templates/Settings.html | Settings UI page |
