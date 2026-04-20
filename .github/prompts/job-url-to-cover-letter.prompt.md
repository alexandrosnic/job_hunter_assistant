---
name: Job URL To Cover Letter
description: "Use when converting one job application URL into a tailored cover letter draft using local candidate materials, then optionally saving the result."
agent: "Job Application Writer"
argument-hint: "Paste one job URL and optional role title."
---
Generate a tailored cover letter from the provided job URL using the Job Application Writer workflow.

Execution requirements:
1. Read source folder paths from `.local/config.json`.
2. Use only the latest CV file from `cvDir`.
3. Reuse `.local/candidate-profile-cache.json` if source files are unchanged; otherwise refresh it.
4. Extract job requirements from the provided URL.
5. Match requirements to strongest candidate evidence.
6. Draft one high-quality cover letter in the candidate's tone.
7. Return output in this order:
- Candidate profile summary
- Requirement-to-evidence mapping
- Final cover letter draft
8. Ask whether to save before writing any output file.
9. If approved, save to `output/cover-letters/<yyyy-mm-dd>-<company>-cover-letter.md`.

Input:
- Job URL: ${input:jobUrl}
- Optional role title: ${input:roleTitle}
