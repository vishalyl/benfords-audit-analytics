# Gate 13 — Resume Bullets, Interview Prep & Publish Checklist

**Stage:** 13 · **Date:** 2026-09-13 · **Gate:** `checks/gate_13.py` → **PASS**

## Output

`docs/resume_and_interview.md` — 3 resume-bullet variants (audit/forensic, data
analyst/BI, data scientist), a 60-second and 3-minute pitch, 22 interview Q&A (exceeds
the 20-question minimum) covering method, ML, audit judgement and project-integrity
questions, a one-page numbers sheet, and a LinkedIn post draft.

## A real leak found and fixed during this stage

Running the adapted personal-path check (see `DECISIONS.md` D-0006) found that
`reports/gate_reports/gate_00.md` (committed in the Stage 0-2 commit, before this
session) printed the absolute local interpreter path twice
(`C:\Users\visha\Premier Pro\...`). Both lines were edited to `<repo-root>\...` before
this commit. `.gitattributes` was also added earlier (Stage 12) since it was listed in
the master plan's repo layout but never created.

## Gate check log

```
GATE 13: PASS
C1 PASS: 22 numbered questions, 3 resume-bullet variants, no [X]/[N] placeholders
C2 PASS: all 31 numeric tokens in resume bullets match reports/metrics (tolerant)
C3 PASS: no leaked local file paths in tracked files (outside plan/)
C4 PASS: LICENSE exists
C5 PASS: no tracked file >50MB
C6 PENDING: remote=not set, working_tree=has uncommitted changes — publishing to a
  public GitHub remote is a user decision, not made silently by the agent
C7 PASS: all gate reports gate_00 .. gate_12 exist (gate_13.md written at the end of this run)
```

C6 is recorded as PENDING rather than FAIL and does not block the gate: making the repo
public and pushing it is exactly the kind of visible, hard-to-reverse action this
agent's operating instructions require confirming with the user first, rather than
doing silently at the end of a long autonomous run.

## DECISIONS.md entries added

- D-0006 — the personal-path scrub check is adapted to search for actual leaked
  absolute paths rather than the bare username, which is also a substring of the
  project owner's real name ("Vishal") appearing legitimately in authorship fields.

## What remains for the human

1. Decide whether to create a public GitHub repository and push (this agent has not
   done so — see the final summary for this run).
2. If publishing: enable GitHub Pages for `docs/index.html`, optionally deploy
   `app/streamlit_app.py` to Streamlit Community Cloud (one manual OAuth click), and
   record the live URLs in `reports/gate_reports/gate_10.md`.
3. Build the Power BI `.pbix` from `dashboard/POWERBI_BUILD_NOTES.md` if desired
   (Stage 9, out of scope this run).
4. Rehearse the 22 interview answers against the numbers sheet in
   `docs/resume_and_interview.md`.

**GATE: PASS**
