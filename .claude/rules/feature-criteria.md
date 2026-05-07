# Feature Criteria Quality

Every success criterion in a `*.feature.md` must pass five litmus tests.

## The five tests

1. **Rename test** -- could this criterion survive renaming every variable and function? If it references internal names, it is too coupled to implementation.
2. **Outsider test** -- could someone who has never seen the codebase verify this criterion? If it requires reading source to understand, it is too vague.
3. **Rewrite test** -- could this criterion survive a complete rewrite in a different language/framework? If it depends on a specific library or pattern, it is an implementation detail.
4. **Negation test** -- does the negation of this criterion describe a real failure? If "it does NOT do X" is meaningless, the criterion is not testable.
5. **Stability test** -- will this criterion still be valid after 10 unrelated commits? If minor refactors would break it, it is too brittle.

## Common mistakes
- Criteria that describe implementation steps ("use a dict lookup") instead of observable behavior
- Criteria with no measurable threshold ("should be fast")
- Criteria that duplicate other criteria with different wording
- Criteria that can never fail ("the code exists")
