---
description: "Capture an idea before it is lost. Appends a timestamped entry to IDEAS.md."
agent: "agent"
argument-hint: "<idea>"
---
Capture idea: {{input}}

1. Check if IDEAS.md exists at the repo root. Create it with header `# Ideas` if not.

2. Append a new line: `- YYYY-MM-DD | {{input}}`

3. Confirm with the exact line that was added.
