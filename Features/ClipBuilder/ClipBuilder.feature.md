# Clip Builder

## What It Does

Extracts and compiles video clips from media files. Users search for files, mark clip timestamps on a visual timeline, and export a compilation to a target duration.

## Success Criteria

1. Users can search indexed media files or browse the filesystem to find source videos.
2. A video player with custom controls (speed, seek, scrub) allows previewing source files.
3. Clip start/end markers can be placed with configurable duration (1-120 seconds per clip).
4. A timeline visualization shows all marked clips with zoom support.
5. Compilation export concatenates marked clips to a target length (60 or 120 seconds).
6. An optional 30-second version can be generated alongside the main compilation.
7. Clip presets (saved marker positions) can be saved and loaded for reuse.
8. The /ClipBuilder page provides the full clip workflow from search to export.

## Status

COMPLETE

## Scope

```
Features/ClipBuilder/**
```

## Files

| File | Role |
|------|------|
| Features/ClipBuilder/ClipBuilderController.py | Flask Blueprint -- clip builder endpoints |
| Features/ClipBuilder/ClipBuilderBusinessService.py | Clip extraction and compilation logic |
| Templates/ClipBuilder.html | Clip builder UI page |
