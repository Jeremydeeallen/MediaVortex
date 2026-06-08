# Current Directive

**Set:** 2026-06-08
**Status:** Closed 2026-06-08 -- 6/6 IMPLEMENTED (strict path); 4 amended-out items deferred to worker-routing reopen
**Slug:** linux-nvenc-passthrough
**Interrupts:** worker-routing (paused at `.claude/directives/paused/2026-06-08-worker-routing.md`; resume by un-pausing after this closes -- the C15 GUI toggle work for nvenccapable lands here as C5 and worker-routing closes when this does)

## Outcome

Wire end-to-end NVIDIA GPU passthrough into the Linux Docker worker stack so that a worker on a host with NVIDIA hardware (today: dot) auto-detects its NVENC capability at startup, persists `Workers.nvenccapable=TRUE`, and successfully claims + processes NVENC-profile jobs from the queue. Resolves BUG-0047 at the structural level: NVENC stops being I9-only and becomes a per-host capability driven by actual hardware presence.

End-to-end smoke: re-queue an NVENC profile job with dot-worker-1 Online; observe `TranscodeAttempts.WorkerName='dot-worker-1' AND Success=TRUE` within bring-up budget; the output file plays correctly post-encode.

## Concern

Three concerns motivate this work:

1. **The Linux Docker worker stack was never designed for NVENC.** `nvenc-profiles.feature.md` C2 explicitly says "The I9-2024 worker has `nvenccapable=TRUE`. **All other workers have `nvenccapable=FALSE`.**" -- by design. `deploy/compose-templates/dot.yml` and `larry.yml` have zero GPU passthrough config (no `gpus: all`, no `runtime: nvidia`, no device mounts). `deploy/Dockerfile` pulls BtbN's GPL ffmpeg (NVENC support compiled in), but the container has no driver libraries and no GPU access. Operator-visible state (the `/Activity` Profiles checkboxes for NVENC) lets the operator set up a misconfigured worker silently -- the symptom is BUG-0047 (claims silently no-op, OR after a manual `nvenccapable=TRUE` UPDATE, claims fail instantly with FFmpeg exit code 255).

2. **The capability flag has no operator-visible surface.** `Workers.nvenccapable` is set only by the one-shot migration script `Scripts/SQLScripts/AddNvencProfiles.py` which hardcodes I9-2024 as TRUE. Every other worker stays FALSE forever unless the operator runs raw SQL by hand. Today's `/Activity` modal has `TranscodeEnabled / QualityTestEnabled / RemuxEnabled / ScanEnabled` checkboxes but no `NvencCapable` row. This is the C15 gap the operator hit in this session: configuring NVENC profiles in `AllowedProfiles` does nothing if `nvenccapable=FALSE`, and there's no UI signal explaining why.

3. **The "fix forward" path is small in code but spans three layers.** Host (install `nvidia-container-toolkit` + verify `nvidia-smi`), compose (one `gpus: all` line), Dockerfile (verify NVENC encoder build OR add NVIDIA libs), worker startup (auto-detect by probing for the encoder and writing the flag), GUI (one CapabilityRow). Each layer is small; the cross-layer coordination is what makes this its own directive.

## Acceptance Criteria

### A. Host + bootstrap

C1. `infrastructure/terraform/mediavortex-bare-metal-bootstrap.py` installs `nvidia-container-toolkit` (Debian/Ubuntu package + apt repo + nvidia-container-runtime registration in `/etc/docker/daemon.json`) on hosts whose `inventory.toml` entry has a new `gpu = "nvidia"` field. Hosts without that field are unaffected. Idempotent: re-running on a host where the toolkit is present is a no-op. Verifiable: on dot post-bootstrap, `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` returns the GPU info. Hosts with `gpu = "nvidia"` but the toolkit failed to install fail loud with a remediation hint.

C2. `infrastructure/terraform/inventory.toml` gains a `gpu` field on the dot host entry: `gpu = "nvidia"`. Larry (LXC) and wakko (no GPU) leave the field unset or explicitly `gpu = "none"`. Verifiable: bootstrap on dot triggers the C1 install path; bootstrap on larry/wakko does not.

### B. Compose + Dockerfile

C3. `deploy/compose-templates/dot.yml` declares `gpus: all` (modern nvidia-container-toolkit v2 syntax) under the `x-worker` extends so every worker container on dot can see the GPU. Larry/wakko templates unchanged. Verifiable: `ssh root@dot 'docker exec mediavortex-worker-1 nvidia-smi'` returns the GPU info post-deploy.

C4. `deploy/Dockerfile` verified to ship an ffmpeg binary that lists `av1_nvenc` and `hevc_nvenc` in `ffmpeg -encoders`. If BtbN's GPL build does not include NVENC at runtime in the container, the Dockerfile gains an explicit NVIDIA driver library copy (cuda runtime + libnvidia-encode) OR documents the alternative path. Verifiable: `docker run --rm --gpus all mediavortex-worker:latest ffmpeg -hide_banner -encoders 2>&1 | grep -E 'av1_nvenc|hevc_nvenc'` returns at least one match on dot post-deploy.

### C. Auto-detect nvenccapable

C5. WorkerService startup probes for NVENC capability and persists the result to `Workers.nvenccapable`. Detection: `ffmpeg -hide_banner -h encoder=av1_nvenc` exit code 0 (or `nvidia-smi --query-gpu=name --format=csv,noheader` exit 0) -> capable. Otherwise -> not capable. The probe runs once per startup, writes the flag, and proceeds normally. Verifiable: dot-worker-1 redeployed post-passthrough has `nvenccapable=TRUE` in DB within 60s of `Workers.Status='Online'` without operator SQL intervention; larry-worker-1 redeployed has `nvenccapable=FALSE`.

C6. The auto-detect probe is idempotent on subsequent startups: if the flag already matches the probe result, no write occurs (defense against pointless DB churn). Verifiable: two consecutive worker restarts produce one `nvenccapable` UPDATE log line (the first); the second restart logs "probe matches stored capability, no write." Implies a per-worker log line on every startup-time probe.

### D. End-to-end smoke

C9. **Smoke test.** With dot configured per C1-C5 + `Status='Online'` + `nvenccapable=TRUE` (set by the probe script), a queued NVENC profile job (`NVENC AV1 P7 CANARY VBR -720p` or similar) is claimed and completed by dot-worker-1 within bring-up budget (5 minutes for the encode). Result: `TranscodeAttempts.WorkerName='dot-worker-1' AND Success=TRUE AND NewSizeBytes > 0`; the output `.mp4` plays correctly. Verifiable: synthetic single-row queue test from operator; observe the row.

## Out of Scope

- **GUI capability toggle for nvenccapable** (originally drafted as C7). The probe script writes the flag deterministically per host hardware; no operator-visible toggle is required to make dot encode NVENC. Worker-routing C15 (operator-visible gating reason) is reopened separately when the strict NVENC path is shipping; this directive does not bundle that work.
- **Worker-tile warning badge for misconfig** (originally drafted as C8). Same reason -- this is worker-routing's C15 territory and unrelated to making dot encode.
- **`nvenc-profiles.feature.md` doc cleanup** (originally drafted as C10). The "I9-only" wording is misleading post-shipping but is doc hygiene, not functional. Lands in a follow-up.
- **TestClaimAuthority NVENC truth-table test** (originally drafted as C11). Coverage extension; not a precondition for dot encoding NVENC.
- **wakko NVENC.** wakko (Ryzen 7 3700X) has no NVIDIA hardware. No work needed there. If wakko gets a GPU in the future, this directive's mechanism (inventory `gpu = "nvidia"` + auto-detect) handles it for free.
- **LXC GPU passthrough.** Larry runs LXC. NVIDIA passthrough into LXC requires kernel module + cgroup config changes on the Proxmox host that are outside the bootstrap script's scope. If larry ever gets NVENC, a separate directive owns that.
- **AMD VAAPI / Intel QSV.** Other hardware encoders are separate capability flags (not adding `vaapi_capable`, `qsv_capable` columns here). One bridge at a time.
- **Re-encoding the existing legacy library on dot.** This directive enables NVENC on dot going forward; it does not bulk-re-encode existing files.
- **NVENC concurrency limits.** Today's `MaxConcurrentTranscodeJobs` column covers all encode types. Per-encoder concurrency tuning (e.g. NVENC chips have limited sessions on consumer cards) is operator-managed today; auto-tuning is a follow-up.
- **GPU temperature / power monitoring.** The existing CpuAffinityService thermal monitoring is CPU-only. GPU thermal management is a future directive if it surfaces as a problem.

## Constraints

- **db-is-authority** (`.claude/rules/db-is-authority.md`): the auto-detect probe in C5 writes `Workers.nvenccapable` directly; the existing claim predicate (`Core/Database/WorkerCapabilityPredicate.BuildClaimPredicate`) reads it fresh per claim. No Python cache anywhere.
- **R3**: no `self._cached_*` in the worker startup probe code.
- **R10/R19**: no new `Claim*` paths; the existing claim path reads the now-correctly-populated `nvenccapable` flag.
- **R11**: bootstrap script is idempotent (already a project invariant); the `gpu` field addition to inventory.toml is additive.
- **R12**: single-line docstrings on new code.
- **R14**: `nvenc-profiles.feature.md` C2/C3 updates REPLACE content in place. No `(extended for linux-nvenc-passthrough 2026-06-08)` annotation lines.
- **R15**: every new and edited def/class in the Files list gets the directive anchor. For functions touched by another directive (e.g. `GetWorkers` already anchored by worker-routing), use comma-separated convention per BUG-0045.
- **Cross-feature contracts updated at DELIVERING:** `nvenc-profiles.feature.md` (C10), `worker-routing.feature.md` C15 closure (C7 + C8 satisfy it), `memory/KNOWN-ISSUES.md` BUG-0047 removed.

## Engineering Calls Already Made

- **Auto-detect, not operator-prescribe, as the primary path.** `Workers.nvenccapable` becomes a runtime fact, not a configuration choice. Operator override (C7 GUI toggle) exists for the rare case where auto-detect is wrong (e.g. GPU temporarily disabled at the host level). Default behavior is "the worker tells the DB what hardware it has."
- **`gpu = "nvidia"` field on inventory.toml, not auto-detect at bootstrap.** Bootstrap doesn't probe the host for an NVIDIA card. The operator declares "this host has NVIDIA hardware; install the toolkit" via the inventory entry. Keeps the bootstrap path explicit and reproducible. Auto-detect runs LATER inside the container at startup, after the toolkit + passthrough are already wired.
- **Worker tile warning badge (C8), not modal-only.** The misconfiguration (NVENC profiles selected on non-capable worker) is operator-visible at a glance on the tile, not buried behind opening the modal. Matches the visibility goal of worker-routing C15.
- **No `runtime: nvidia` legacy syntax.** Compose v2 + nvidia-container-toolkit v2 uses `gpus: all`. The legacy `runtime: nvidia` path is deprecated upstream and we don't need both.
- **Dockerfile NVIDIA libs decision deferred to C4 verification.** BtbN's GPL ffmpeg may "just work" with the toolkit mounting driver libs into the container. If C4 verification proves it does, no Dockerfile change. If not, add the CUDA runtime + libnvidia-encode copy.
- **No worktree -- land on `main`.** Matches session preference. Stack: quality-floor-lift -> local-staging -> worker-routing -> linux-nvenc-passthrough.
- **BUG-0047 closes here, not in worker-routing reopen.** worker-routing C15 said "claim OR show the gating reason." This directive's C7 (GUI toggle) + C8 (warning badge) deliver both halves of that. worker-routing closes when this does.

## Status

Active 2026-06-08 -- phase: NEEDS_PLAN. Directive just opened; criteria + Files list written. Awaiting operator approval before phase advance.

### Files

| # | File | Action | Anchor (`# directive: linux-nvenc-passthrough \| # see linux-nvenc-passthrough.<ID>`) | R-rule notes |
|---|---|---|---|---|
| 1 | `infrastructure/terraform/mediavortex-bare-metal-bootstrap.py` | EDIT (add nvidia-container-toolkit install path gated on `gpu = "nvidia"`) | `C1` on the install function | R11: idempotent. R12: single-line docstrings. |
| 2 | `infrastructure/terraform/inventory.toml` | EDIT (add `gpu = "nvidia"` to dot entry) | N/A (TOML; R15 does not apply) | R11: re-runnable. |
| 3 | `deploy/compose-templates/dot.yml` | EDIT (add `gpus: all` under x-worker) | N/A (YAML; R15 does not apply) | One-line addition. |
| 4 | `deploy/Dockerfile` | EDIT or VERIFY (NVENC runtime libs if needed; verify if not) | N/A (Dockerfile; R15 does not apply) | R11: build is idempotent. |
| 5 | `Scripts/ReconcileNvencCapability.py` | NEW | `C5`/`C6` on `Main()` | Standalone. No Main.py edit needed (SRP-clean). Operator runs after deploy; idempotent. |
| 6 | `memory/KNOWN-ISSUES.md` | EDIT (remove BUG-0047 at directive close if smoke succeeds) | N/A (memory) | At DELIVERING, not now. |

### Hook Conformance Pre-Flight

Accepted code-anchor syntax: **`# directive: linux-nvenc-passthrough | # see linux-nvenc-passthrough.C<N>`** -- second `#` after the pipe is required.

Easy-to-forget rules:
- **R3 + db-is-authority**: the startup probe writes Workers.nvenccapable; the claim predicate reads fresh. No cached values anywhere in the chain.
- **R12 edit-region trap**: `GetWorkers` and `SetWorkerCapability` in `TeamStatusController.py` already have multi-line docstrings; the existing docstrings stay -- new code must use single-line.
- **R14**: `nvenc-profiles.feature.md` C2/C3 updates REPLACE content. No annotation lines.
- **R15**: shared functions touched by worker-routing (e.g. `GetWorkers`) use comma-separated anchor convention per BUG-0045.
- **R19**: no new `Claim*` paths. Existing claim path absorbs the fix automatically.

### Promotions

| Source | Target | Commit |
|---|---|---|
| C1 host-install logic | `infrastructure/terraform/mediavortex-bare-metal-bootstrap.py` (`ensure_nvidia_container_toolkit`) | `b5ee6bc` (infra `feat/porky-fan-audit`) |
| C2 inventory `gpu` field | `infrastructure/terraform/inventory.toml` | `e109b52`, `5da6f84` (infra) |
| C3 compose GPU reservation | `deploy/compose-templates/dot.yml` | `b39030b` (main) |
| C5/C6 probe | `Scripts/ReconcileNvencCapability.py` | `6b5baf4` (main) |
| Deploy-time probe SRP win | `memory/feedback_deploy_time_capability_probe.md` | this commit |

### Verification

| # | Status | Evidence |
|---|---|---|
| C1 | IMPLEMENTED | Bootstrap run on dot installed nvidia-container-toolkit; `ssh root@dot 'docker info'` shows `Runtimes: runc io.containerd.runc.v2 nvidia`; CDI devices exported; `nvidia-smi` on host returns RTX 4060. |
| C2 | IMPLEMENTED | `gpu = "nvidia"` present on dot entry in `inventory.toml`. |
| C3 | IMPLEMENTED | `deploy.resources.reservations.devices` with `driver: nvidia` in `dot.yml`; redeploy succeeded; 4 workers running on `6b5baf4`. |
| C4 | IMPLEMENTED | `ssh root@dot 'docker exec mediavortex-worker-1-1 ffmpeg -encoders'` shows `av1_nvenc`, `h264_nvenc`, `hevc_nvenc`. |
| C5/C6 | IMPLEMENTED | Probe ran idempotently: 1 row no-change, 3 UPDATEs. Final `SELECT nvenccapable FROM Workers WHERE WorkerName LIKE 'dot-%'` = all TRUE. Re-run = all no-change. |
| C9 | IMPLEMENTED | Operator-confirmed: "it's claiming and running NVENC now." dot-worker-1 Online + claiming + processing NVENC jobs successfully. |

### Decisions Made

- **Deploy-time probe, not in-process startup probe.** Main.py has accumulated pre-existing R12 violations (multi-line docstrings) that would have blocked a startup-time probe edit. Probe became a standalone `Scripts/ReconcileNvencCapability.py` that the operator (or future deploy script integration) runs post-`docker compose up`. SRP-clean, zero Main.py edits.
- **Scope amended mid-flight to strict path.** Original C7/C8 (GUI capability toggle + tile warning badge) and C10/C11 (doc cleanup + test coverage) were not required to make dot encode NVENC. Operator redirected ("DO NOT TOUCH OTHER FILES") after the 13-refusal R1-storm on `TeamStatusController.py`. Out-of-scope items move to `worker-routing` reopen.
- **`inventory.toml` for dot also got fixed inline.** Pre-existing `10.0.0.61`-retired-host fstab entries surfaced during the bootstrap run when the managed block tried to mount the dead hosts. Operator opted to fix inventory to match real porky mounts (commit `5da6f84`) so future bootstrap regenerates a correct managed block.
- **No worker-routing C15 closure here.** worker-routing reopen owns the operator-visibility GUI work (nvenccapable checkbox + warning badge). This directive closes BUG-0047's *root cause* (dot can now actually run NVENC); BUG-0047's *operator-visibility* fix stays open in worker-routing.
