# Smoke Assets

Registry of local read-only source files used as smoke-test canaries. Not managed by MediaVortex scans. Not on network shares. Copy to a StorageRoot when needed for a live smoke; refresh from here if the pipeline destroys the disk copy.

## Assets

| Asset | Local read-only path | Container | Duration | Video | Audio | Subs | Purpose |
|---|---|---|---|---|---|---|---|
| Hotel Chevalier (2007) Bluray-1080p | `C:\Users\jerem\Videos\Hotel Chevalier (2007) Bluray-1080p.mkv` | mkv | ~13 min | h264 1080p ~11 Mbps | ac3 5.1 English | subrip English | Reencode + VMAF + Replace + subtitle-preservation smoke. Live-action Bluray with SRT subs. |

## Rules

- **Read-only.** Files have Windows read-only attribute set. Do not clear it.
- **Do not scan.** Directory is not a MediaVortex StorageRoot.
- **Refresh workflow.** Smokes always enqueue against the network StorageRoot copy (`M:\Hotel Chevalier (2007)\...`), NOT the read-only master. Before smoke: if network copy is missing or damaged, copy the master from `C:\Users\jerem\Videos\` to `M:\Hotel Chevalier (2007)\`, refresh MediaFiles row (rescan MFID 620351 OR manual UPDATE of StorageRootId + RelativePath + Codec + Container + SizeMB), then enqueue against MFID 620351. Pipeline mutates the network copy; master stays intact for the next refresh.
- **Add assets by appending to the table.** Each row names the read-only path + shape + smoke purpose.
