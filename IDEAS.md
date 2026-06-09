# Ideas

- 2026-06-06 | Multiple audio languages: keep current behavior as default track; add 2nd audio track with aggressive dialogue enhancement (night mode / hearing-impaired compression) for older ears
- 2026-06-09 | Push compliance Gates into a SQL view (`v_MediaFilesGateStatus` = `MediaFiles CROSS JOIN ComplianceGates` + first-fail CASE WHEN). Collapses the 8 `IComplianceGate` impls + chain + interface from the compliance-solid-refactor directive into one view + ~30 LOC Python reader; `RecomputeForFiles` becomes a single SQL UPDATE for the gate column. Considered for the original directive, deferred to a follow-up after the engine shipped.
