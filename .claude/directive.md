# Current Directive

<!--
This file is auto-loaded into Claude's context every session.
When this file contains a non-empty directive, CEO mode is active
(see .claude/rules/ceo-mode.md). When empty, task-delegation mode applies.

Replace everything below this comment block with your directive when ready.
A good directive has the following sections.
-->

## Outcome

<!-- One paragraph. What does production look like when this directive is satisfied?
     Describe behavior, not implementation. Example:

     "The pipeline runs unattended for 30 days without generating new
     -mv-mv files, without orphan disk artifacts, and without stale-metadata
     drift in MediaFiles. An operator can answer 'why didn't this file
     transcode' with a single SQL query against TranscodeAttempts.Disposition
     and DispositionReason." -->

(none — directive not yet set)

## Acceptance Criteria

<!-- Each criterion must pass the 5 litmus tests from .claude/rules/feature-criteria.md:
     rename / outsider / rewrite / negation / stability.

     Each criterion is verifiable from the outside (SQL query, file check, observable
     behavior, log assertion). Avoid implementation references ("must use X library").
     Number them so they can be cited.

     Tight criteria = autonomous delivery. Loose criteria = escalation churn. -->

(none)

## Out of Scope

<!-- What this directive explicitly does NOT cover. Anti-scope statements
     help Claude resist the temptation to expand. Example:

     - v2 architecture decisions (separate directive)
     - Other tables' persistence drift (track separately)
     - UI / Activity page redesign -->

(none)

## Constraints

<!-- Non-negotiable conditions. Things like:

     - "Cutover must not exceed 30 min worker downtime"
     - "No destructive schema changes without explicit confirm"
     - "No production deploy on Fridays"
     - "Preserve existing operator queries against TranscodeAttempts" -->

(none)

## Escalation Defaults

<!-- Optional. Pre-resolved answers for predictable ambiguities, so Claude
     doesn't have to escalate them. Example:

     - "When a tradeoff is between code complexity and operator visibility,
        pick operator visibility."
     - "When a tradeoff is between rollout speed and data safety,
        pick data safety."
     - "Default risk tolerance: low. Stage changes through canary first." -->

(none)

## Status

<!-- Set by Claude as work progresses. Operator reads this for status. -->

NOT STARTED
