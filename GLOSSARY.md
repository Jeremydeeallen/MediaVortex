# Glossary

**Purpose:** Single-source-of-truth terminology across MediaVortex. Every entry names an authoritative source (feature doc, flow doc, rule, standards row, or code path). Deprecated terms carry a replacement pointer. Four buckets: **Project vocabulary**, **Media / encoding**, **Job model**, **Infrastructure**.

**Not here:** implementation detail (belongs in feature/flow docs) and phase/rule specifics (belongs in `.claude/standards/index.md` and `.claude/rules/`).

## Project vocabulary

- **Anchor** -- one-line inline pointer `# see <slug>.<W|S|C|ST><N>` above a `def` / `class`. Enables R1 partial-Read acceptance of a flow doc. Source: `CLAUDE.md` Reading order; `.claude/rules/flow-docs.md`.
- **CEO mode** -- operator sets outcome-level acceptance criteria; Claude owns design + implementation + delivery judgment; escalates only for irreversible operations, criteria ambiguity, missing domain data, scope conflict, or schedule risk. Source: `.claude/rules/ceo-mode.md`.
- **Compliance booleans** -- per-domain per-file `*Compliant` booleans (AudioNormalization / VideoEncoding / ContainerFormat). Feed the GENERATED `MediaFiles.WorkBucket`. Written only by owning vertical. Source: `ARCHITECTURE.md#database-invariants`.
- **Directive** -- transient CEO ask; owns outcome + criteria + plan + in-flight state. Lives at `.claude/directive.md`; closed at `.claude/directives/closed/YYYY-MM-DD-<slug>.md`. Not a contract. Source: `.claude/rules/doc-layering.md`.
- **Feature doc** -- durable contract for one vertical; colocated `*.feature.md`. Owns Workflows + Success Criteria + intra-feature Seams. IDs `W<N>` / `C<N>` / `S<N>` stable. Source: `.claude/rules/feature-docs.md`.
- **Flow doc** -- durable contract for one pipeline; colocated `*.flow.md`. Nav hub for pipeline-shaped code. Owns Stages + cross-stage Seams. IDs `ST<N>` / `S<N>` stable. Source: `.claude/rules/flow-docs.md`.
- **Phase** -- directive state in `NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING`. Gates tool access. Source: `.claude/standards/index.md`.
- **Promotions** -- `### Promotions` rows in a directive: durable content moved from directive into a `*.feature.md` / `*.flow.md`. Required non-empty at DELIVERING. Source: `.claude/rules/doc-layering.md`.
- **R-rule** -- numbered mechanical content rule (`R1`..`R19`); each hooks a function in `.claude/hooks/pre-edit-standards.ps1`. Source: `.claude/standards/index.md`.
- **Seam** -- directional boundary between components (function-call, wire-format, state-store, UI, process). Enumerated before IMPLEMENTING; round-tripped at VERIFYING. Source: `.claude/rules/seam-verification.md`.
- **Slug** -- top-level addressing primitive for docs + directives. Lowercase filename without `.feature.md` / `.flow.md` extension. R16-enforced in first 15 lines of every feature/flow doc. Source: `.claude/rules/feature-docs.md`, `.claude/rules/flow-docs.md`.
- **Standards index** -- mechanically enforced phase-gate + R-rule table. Authoritative for what the hook refuses. Source: `.claude/standards/index.md`.
- **Task-delegation mode** -- fallback when directive is empty AND `.claude/.task-delegation-on` present; scope-discipline task contracts replace directive scope. Operator-only toggle. Source: `.claude/rules/ceo-mode.md`.
- **Vertical** -- one feature-scoped module in `Features/<Name>/`. Owns one bounded concern + its `*.feature.md`. Source: `ARCHITECTURE.md#vertical-roster`.
- **WorkBucket** -- GENERATED column on `MediaFiles`; classifies file into one of a fixed set of work categories (compliant / audio-fix / etc.) via CASE over the compliance booleans. Postgres refuses direct writes. Source: `ARCHITECTURE.md#database-invariants`; `Features/WorkBucket/work-bucket.flow.md`.

## Media / encoding

- **AudioFix** -- deprecated ProcessingMode label; now Plan variant with `VideoOp=StreamCopy + AudioOp=Reencode`. Source: `transcode.flow.md`.
- **BypassReplace** -- **deprecated** Disposition value. Retired by `transcode-flow-canonical` C6. Replacement: real verify + `Replace` / `Reject` / `Requeue`. Source: `transcode-flow-canonical` C6.
- **Checksum verify** -- StreamCopy strategy's verification method: video stream bit-identical between source and output. Emits `Vmaf=100.0` with `Method=Checksum`. Source: `transcode.flow.md` ST8 Strategy Verify.
- **Container-only fix** -- Plan variant `VideoOp=StreamCopy + AudioOp=StreamCopy + ContainerOp=Change`. Rewraps into target container without re-encoding. Source: `transcode.flow.md`.
- **Demucs pre-pass** -- ML source separation to isolate dialog before Dialog Boost track emit. Source: `Features/AudioNormalization/audio-normalization.flow.md`.
- **Dialog Boost** -- forced-stereo Track 1 with dialog isolated + emphasized. `Track 1.disposition.default=1`; Track 0 (original) `default=0`. Source: `Features/AudioNormalization/`; audio-dialog-boost-real closed directive.
- **Disposition** -- verify outcome per `TranscodeAttempts` row. Valid post-cutover: `Replace` / `Reject` / `Requeue`. See BypassReplace (deprecated). Source: `transcode.flow.md` ST9 ACTION.
- **EBUR128** -- FFmpeg loudness measurement filter. `Summary:` block is the only reliable parse anchor (silence-floor progress lines otherwise leak). Source: memory `feedback_ebur128_parser_anchor`.
- **FFmpeg / FFprobe** -- transcoder + prober binaries. FFprobe reads metadata; FFmpeg produces output. Source: `ARCHITECTURE.md#topology`.
- **Linear loudnorm** -- audio loudness normalization mode preserved by `linear-loudnorm.feature.md`. Enforcement: `Tests/Contract/TestLinearLoudnormEnforcement.py`. Source: `Features/AudioNormalization/linear-loudnorm.feature.md`.
- **LUFS** -- Loudness Units relative to Full Scale. Track 0 integrated LUFS target read from `TargetIntegratedLufs`. Source: `Features/AudioNormalization/`.
- **NVENC** -- NVIDIA hardware encoder. Gated by `Workers.nvenccapable` flag. Post-deploy capability probe, not startup-time. Source: memory `feedback_deploy_time_capability_probe`.
- **Plan** -- per-job encode plan: `{VideoOp, AudioOp, SubtitleOp, ContainerOp}` where each Op is `Reencode` / `StreamCopy` / `Copy` / `Change` / `Drop`. Variance lives in Plan; orchestration is Plan-blind. Source: `transcode.flow.md`.
- **Probe** -- FFprobe pass at ST3 that fills `MediaFiles.Resolution` + audio/subtitle stream metadata. Source: `transcode.flow.md` ST3.
- **Profile** -- named encode configuration (bitrate, codec, container, thresholds). Rows in `Profiles`; thresholds in `ProfileThresholds`. Read-only at CommandBuilder + decision layers. Source: `Features/Profiles/`.
- **Quick** -- deprecated ProcessingMode label; smoke-path fast encode. Now Plan variant. Source: `transcode.flow.md`.
- **Reencode** -- Strategy that produces a new encoded video stream. Verify method: VMAF. Source: `transcode.flow.md` ST5 Strategy variants; `Features/TranscodeJob/Worker/Strategies/`.
- **Remux** -- **deprecated** as a top-level job type / ProcessingMode. Now Plan variant `VideoOp=StreamCopy`. `remux.flow.md` deleted; see `transcode.flow.md`. Source: `transcode-worker-unification` closed directive; `transcode-flow-canonical` C1.
- **StreamCopy** -- Strategy that copies streams without re-encoding. Verify method: checksum. Source: `transcode.flow.md` ST5; `Features/TranscodeJob/Worker/Strategies/`.
- **SubtitleFix** -- deprecated ProcessingMode label; now Plan variant with `SubtitleOp=Change`. Source: `transcode.flow.md`.
- **Transcode** -- **ambiguous** term: (a) umbrella name for the whole FFmpeg-driven job type (see `TranscodeQueue`, `TranscodeJob`, `TranscodeAttempts`); (b) old ProcessingMode label meaning "re-encode". Meaning (b) is deprecated; use Reencode Strategy. Umbrella rename to `MediaJob*` filed at `IDEAS.md`. Source: `transcode-flow-canonical` Engineering Calls; `IDEAS.md`.
- **VMAF** -- Netflix perceptual quality score (0-100). Reencode strategy's verify method. Threshold `>= 80` gates Replace disposition. Source: `Features/QualityTesting/`.
- **Verify** -- Strategy hook at ST8. Reencode -> VMAF; StreamCopy -> checksum. Both write `Vmaf` column semantically (checksum path writes 100.0 on match). Source: `transcode.flow.md` ST8; `transcode-flow-canonical` Engineering Calls.

## Job model

- **AddJobToQueue** -- canonical admission entry point on `TranscodeQueue`. All producers (web GUI, scanner, requeue, canary, smoke) converge here. Source: `Features/TranscodeQueue/QueueManagementBusinessService.py`; `transcode-flow-canonical` C2.
- **BuildClaimPredicate** -- single-source SQL fragment emitter for worker-capability gates. All `Claim*` queries route through it. Whitelist-guarded against SQL injection. Source: `Core/Database/WorkerCapabilityPredicate.py`; `.claude/rules/db-is-authority.md`; R10.
- **Claim** -- worker's read + atomic status-transition on a queue row. Every `Claim*` function uses `BuildClaimPredicate`. Source: `.claude/rules/db-is-authority.md`.
- **Force add** -- `TranscodeQueue.AddJobToQueue(ForceAdd=True)` bypasses "already exists" skip. Contract: returns `Success=True, Skipped=False` on insert. BUG-0078 fix. Source: `transcode-flow-canonical` C2.
- **Job type** -- three FFmpeg-driven types (`Transcode` / `QualityTest` / `Scan`); each maps to one `Workers.<Capability>Enabled` flag + one `*.flow.md`. New job type requires distinct capability flag. Source: `ARCHITECTURE.md#job-types`.
- **JobProcessor** -- Template Method base class for worker execution. Owns orchestration; hooks (`Encode` / `Verify`) delegated to Strategy. Source: `Features/TranscodeJob/Worker/JobProcessor.py`; `Features/TranscodeJob/Worker/Strategies/`.
- **Post-transcode gate** -- compliance gate after ST8 Verify. Configured in `PostTranscodeGateConfig`. Not bypassable per C6. Source: `Features/QualityTesting/`.
- **ProcessingMode** -- **deprecated** column-level discriminator (`Transcode` / `Remux` / `AudioFix` / `SubtitleFix` / `Quick`). Replacement: Plan `{VideoOp, AudioOp, SubtitleOp, ContainerOp}`. Existing rows remain until schema migration. Source: `transcode-flow-canonical` C4.
- **QualityTest** -- non-encode job type: re-runs verify against existing attempt. Capability `QualityTestEnabled`. Source: `ARCHITECTURE.md#job-types`.
- **Requeue** -- Disposition value that inserts a new `TranscodeQueue` row via `AddJobToQueue`. BUG-0079 fix. Source: `transcode-flow-canonical` C6.
- **Scan** -- job type: walk storage roots + FFprobe. Capability `ScanEnabled`. Source: `ARCHITECTURE.md#job-types`.
- **Strategy** -- per-Plan variant hook implementation. Registered in `JobProcessorRegistry`. Owns `Encode()` + `Verify()`; nothing else. Source: `Features/TranscodeJob/Worker/Strategies/`.
- **TranscodeAttempts** -- one row per completed attempt. Shared output shape. Every strategy populates `AudioPolicyResolved` / `AudioPolicyJson` / `AudioTracksEmittedJson` / `Vmaf` / `Disposition`. Column `ffpmpegcommand` (double `p`) is a known typo. Source: `CLAUDE.md#database`; `transcode-flow-canonical` C5.
- **TranscodeJob** -- vertical that runs claimed jobs. Owns JobProcessor + Strategies. Source: `Features/TranscodeJob/`.
- **TranscodeQueue** -- one row per pending job. Populated by all admission producers. Consumed by JobProcessor via `ClaimNextPendingJob`. Source: `Features/TranscodeQueue/`.

## Infrastructure

- **CT 203** -- Proxmox LXC container hosting PostgreSQL 16 at `10.0.0.15:5432`. DB / user / password all `mediavortex`. Source: `CLAUDE.md#database`.
- **CT 218 (Larry)** -- Proxmox LXC container hosting Docker + 8 worker containers. `pct exec 218 -- docker exec mediavortex-worker-N-1 ...`. Source: memory `reference_worker_containers_on_larry`.
- **DatabaseService** -- `Core/Database/DatabaseService.py`. `ExecuteQuery` for SELECT (returns `list[CaseInsensitiveDict]`); `ExecuteNonQuery` for INSERT/UPDATE/DELETE (auto-commits). Source: `CLAUDE.md#key-patterns`.
- **I9** -- dev workstation. Reads `C:\Code\MediaVortex` source tree directly on restart -- no redeploy. Owns full WebService/WorkerService start/stop/restart authority per operator. Source: memory `feedback_i9_worker_is_active_codebase`, `feedback_user_starts_webservice`.
- **Jellyfin** -- downstream media server. Post-replace notification via `/Library/Media/Updated` (204 = queued; ~60s coalescing window). Source: memory `reference_jellyfin_notify_api`.
- **LocalPath** -- `Core/Path/LocalPath` module. Shape-agnostic path ops (`LocalExists`, `LocalBasename`, `LocalDirname`, `LocalJoin`, `LocalSplitExt`, `LocalIsFile`, `LocalIsDir`, `LocalGetSize`, `LocalGetMTime`). R6 refuses `os.path.*` on path-named variables. Source: `CLAUDE.md#key-patterns`; R6.
- **LoggingService** -- `Core/Logging/LoggingService`. `LogInfo(msg, ClassName, MethodName)` / `LogException(msg, exception, ClassName, MethodName)`. Source: `CLAUDE.md#key-patterns`.
- **MEDIAVORTEX_DB_HOST** -- env var for DB host override (defaults to localhost on user level). Source: `CLAUDE.md#database`.
- **NFS** -- protocol for Linux worker containers reading media storage. Microsoft NFS client against Linux nfsd is unreliable -- I9 uses SMB instead. Source: memory `feedback_ms_nfs_client_unreliable`, `project_worker_mount_split`.
- **PathStorage** -- `Core/Path` module. Canonical (DB-stored) vs local (host-specific) path decision. Source: `CLAUDE.md#key-patterns`; `.claude/rules/data-integrity.md`.
- **PostgreSQL 16** -- authoritative data store on CT 203. Encoding UTF-8 mandatory (`LC_COLLATE='en_US.UTF-8'`, `LC_CTYPE='en_US.UTF-8'`, `TEMPLATE=template0`). Source: `CLAUDE.md#database`.
- **ScheduleWakeup / ServiceLifecycleManager** -- `ServiceLifecycleManager` in `StartMediaVortex.py` orchestrates service start/stop. Source: `CLAUDE.md#two-microservices`.
- **SMB** -- protocol I9 uses for media storage. Stable on Windows against the media share. Source: memory `project_worker_mount_split`.
- **StorageRoot** -- named media root path stored in DB; `MediaFiles.RelativePath` is relative to a `StorageRootId`. Source: `Core/Path`.
- **StuckJobDetection** -- watchdog service that freezes stuck jobs. Freeze marks attempt `Success=FALSE` per BUG-0075 fix. Source: `Features/ServiceControl/StuckJobDetectionService.py`.
- **venv** -- Python virtual env at `venv/` repo root. `WebService/venv/` is a separate env with its own installed set. Source: `.claude/rules/python-environment.md`; memory `feedback_webservice_venv_drift`.
- **WebService** -- Flask on port 5000. UI + admission API. No transcoding work. Source: `ARCHITECTURE.md#topology`.
- **WorkerService** -- unified worker process. Reads `Workers.<Capability>Enabled` flags per row to determine which claim queries to run. Source: `ARCHITECTURE.md#topology`.
- **Workers** -- DB table; one row per worker; per-worker capability flags (`TranscodeEnabled` / `QualityTestEnabled` / `ScanEnabled` / `RemuxEnabled` -- last deprecated), `Status`, `nvenccapable`. Source: `.claude/rules/db-is-authority.md`.
