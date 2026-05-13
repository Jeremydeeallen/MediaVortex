---
description: "Use when writing API endpoints, error handling, frontend AJAX calls, or user-facing messages. Covers API response format, loading states, and error display."
applyTo: "**"
---
# Error UX

The app must never appear frozen or show raw errors to the user.

## Verified conventions
- Flask API responses use `{'Success': True/False, 'Message': '...', 'Data': {...}}` format
- LoggingService captures exceptions with class and method context
- Frontend shows loading spinners during API calls (jQuery AJAX)

## Required reading
- `CLAUDE.md` -- API response format section
- `transcode.flow.md` -- failure modes at each stage

## Common mistakes
- Showing a loading screen after the blocking work starts (user sees a freeze, then the spinner)
- Catching an error and showing the raw exception text to the user
- Suppressing errors silently (return Success=True when an operation actually failed)
- Network calls with default timeouts that hang the UX
