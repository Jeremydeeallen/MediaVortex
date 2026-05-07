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
8. QualityTestEnabled (global on/off, default OFF) controls whether VMAF testing runs after transcoding.
9. All settings persist to the SystemSettings table as key-value pairs.
10. The /settings page provides the UI for all configuration.

## Status

COMPLETE

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
