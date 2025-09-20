<!--
Sync Impact Report:
Version change: 1.0.1 → 1.1.0
Added sections: VII. Actual Date and Time (NON-NEGOTIABLE)
Modified principles: None
Removed sections: None
Templates requiring updates: .specify/templates/plan-template.md (version reference updated)
Follow-up TODOs: None
-->

# MediaVortex Constitution
our root folder is /Automation/MediaVortex/

## Core Principles

### I. MVVM Architecture (NON-NEGOTIABLE)
Strict separation of Models, ViewModels, Views, and Controllers; Business logic in Services; Data access through DatabaseManager only; Maintain separation of concerns between components; Follow MVVM pattern exactly as specified in Architecture.md

### II. PascalCase Naming Convention (NON-NEGOTIABLE)
All custom variables, functions, classes, files, tables, columns, routes, and URLs MUST use PascalCase; No camelCase or snake_case allowed; Every word in a name should start with a capital letter; No exceptions for parameters, local variables, or any custom names; Only Python built-ins like __init__, str(), len() can have lowercase

### III. Centralized Logging (NON-NEGOTIABLE)
All operations MUST be logged through LoggingService; Database storage required; Function names and components must be tracked; Logging needs to be the first step of our "slice" or walking skeleton; That way we can track and debug errors easily

### IV. File Operations in Python
All file operations (copy, move, delete, data processing) MUST use Python; Cross-platform compatibility required; File management within the transcoding application should use Python (FileManager class); This ensures consistency, cross-platform compatibility, and better integration with the MVVM architecture

### V. UTF-8 Compatibility
All text processing and file operations MUST support UTF-8 encoding; We need to be compatible with UTF-8

### VI. No Emojis (NON-NEGOTIABLE)
No emojis in any output, code, documentation, or communication; Professional text-only communication required; This applies to all code comments, documentation, error messages, and user-facing text

### VII. Actual Date and Time (NON-NEGOTIABLE)
Cursor MUST get the actual date and time before using it in documentation; Never use placeholder dates or hardcoded timestamps; Always query the system for current date/time when creating or updating documentation; This ensures accuracy and prevents outdated timestamp references

## Development Standards

Code must be prepared but not executed in chat; Provide exact commands to run in copy-paste format when requested only; All other code should be written into the codebase; Assume user is in MediaTranscode directory with venv activated (for new project); Use `py` instead of `python` in all examples; When modifying existing features, maintain consistency with current naming in that feature set and add the feature to the NamingConventionViolations.md file; Specify object type and line numbers for all name changes; Provide the best solution based upon the goal for our design; No emojis in any output; When you find duplicate logic ask which one to keep; If logic is deprecated clean it up and make sure that the new code is used properly everywhere; If there is legacy code make sure the functionality is provided by the new code and then remove it from our codebase

## Quality Assurance

Create `.md` files in `/Media/Docs/Checklists/` for all checklist requests; Architecture documentation goes in `Docs/` (e.g., Architecture.md, Features.md); Do not check things off the checklist until I have verified them and tell you it's done; Use `[ ]` for incomplete items, `[x]` only when actually complete; Include file names and line numbers for completed items; This prevents going off on tangents; Append "MVVM pattern using MVVM architecture" to the end of all checklist items; If scripts will only be used during init (creating tables etc)

## Governance

Constitution supersedes all other practices; Amendments require documentation, approval, migration plan; All PRs/reviews must verify compliance; Complexity must be justified; All code must comply with MVVM pattern and PascalCase naming; Follow MVVM pattern: Models (business logic), ViewModels (presentation logic), Views (UI); Maintain separation of concerns between components; Use PascalCase naming convention throughout the new codebase; Implement decision tree exactly as specified in Architecture.md

**Version**: 1.1.0 | **Ratified**: 2025-01-27 | **Last Amended**: 2025-09-19