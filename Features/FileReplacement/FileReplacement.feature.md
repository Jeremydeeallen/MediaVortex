# File Replacement

## What It Does

Replaces original media files with verified transcoded output. Archives original metadata to MediaFilesArchive, swaps the file on disk, re-probes the new file via MediaProbe, and updates all MediaFiles columns.

## Success Criteria

1. Original file metadata is archived to MediaFilesArchive before any destructive operation.
2. Transcoded file replaces the original at the same path on disk.
3. After replacement, the new file is re-probed and all MediaFiles columns are updated with fresh metadata.
4. TranscodedByMediaVortex is set to true on successfully replaced files.
5. If replacement fails (disk error, size mismatch), the original file is preserved and the error is logged.
6. [BUG] FileReplacement depends on MediaProbe for re-probing after replacement, but there is no explicit interface contract between them. The post-replace flow (archive -> replace -> re-probe -> update MediaFiles) crosses FileReplacement and MediaProbe boundaries with no documented API or failure mode agreement.
7. FileReplacement works on any machine (Windows or Linux). _ProcessCompleteFileReplacement() accepts PathTranslation and translates canonical DB paths to local mount paths before all filesystem operations. InPlace output mode skips shutil.move. No hardcoded Windows paths in the cleanup flow.

## Status

COMPLETE

## Scope

```
Features/FileReplacement/**
```

## Files

| File | Role |
|------|------|
| Features/FileReplacement/FileReplacementBusinessService.py | Replacement logic, archival, re-probe trigger |
| Features/FileReplacement/FileReplacementRepository.py | MediaFilesArchive and MediaFiles update queries |
