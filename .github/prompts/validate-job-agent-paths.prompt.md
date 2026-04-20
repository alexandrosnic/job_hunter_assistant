---
name: Validate Job Agent Paths
description: "Use when checking .local/config.json for required keys, sane values, and path safety before running cover-letter generation workflows."
agent: "agent"
tools: [read, search]
argument-hint: "Run validation for local path config before generating letters."
---
Validate `.local/config.json` and report pass/fail with actionable fixes.

Validation rules:
1. File exists and is valid JSON.
2. Required key exists:
- `sourcesDir` is a non-empty array of non-empty strings
3. Values are not placeholders like `<LOCAL_PATH...>`.
4. Every entry in `sourcesDir` is either:
- a directory-like path, or
- an `http://` or `https://` URL.
5. Warn if any configured local absolute paths appear in tracked files under the workspace.

Output format:
1. Validation result: PASS or FAIL
2. Findings list
3. Suggested fixes
