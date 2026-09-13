# Gate 13: Resume Bullets, Interview Prep & Publish Checklist

**Stage:** 13 · **Date:** 2026-09-13 · **Gate:** `checks/gate_13.py` -> **PASS**

## Output

`docs/resume_and_interview.md`: 3 resume-bullet variants (audit/forensic, data
analyst/BI, data scientist), a 60-second and 3-minute pitch, 22 interview Q&A (exceeds
the 20-question minimum), a one-page numbers sheet, and a LinkedIn post draft. Updated
after the Stage 6 full-population re-run (DECISIONS.md D-0007): headline figures now
cite the full 1,030,804-row population (Precision@500 50.8%, Precision@5,000 45.2%,
composite AP 0.166) rather than the earlier 50,000-row sample's numbers.

## A real leak found and fixed earlier in this project

Running the adapted personal-path check found that `reports/gate_reports/gate_00.md`
printed the absolute local interpreter path twice. Fixed at the source in
`checks/gate_00.py` (a `_redact()` helper), not just the committed file, so it stays
fixed on any future re-run. See DECISIONS.md D-0006.

## Gate check log

```
GATE 13: PASS
C1 PASS: 22 numbered questions, 3 resume-bullet variants, no [X]/[N] placeholders
C2 PASS: all 34 numeric tokens in resume bullets match reports/metrics (tolerant)
C3 PASS: no leaked local file paths in tracked files (outside plan/)
C4 PASS: LICENSE exists
C5 PASS: no tracked file >50MB
C6 PENDING: remote=set, working_tree=has uncommitted changes, publishing to a public
  GitHub remote is a user decision, not made silently by the agent
C7 PASS: all gate reports gate_00 .. gate_12 exist (gate_13.md written at the end of this run)
```

C6 is recorded as PENDING rather than FAIL and does not block the gate: the remote is
already configured (the repo was made public earlier in this project), and the
"uncommitted changes" state simply reflects that this pass's edits have not yet been
committed at the moment this check runs.

## DECISIONS.md entries added (this project, cumulative)

- D-0005: README number provenance (placeholder table + hand-checked prose).
- D-0006: personal-path scrub check adapted for the owner's real name.
- D-0007: Stage 6 full-population re-run, the LOF wiring bug it exposed, and a
  determinism false-failure in gate_08 caused by an asymmetric CSV round trip.

## What remains for the human

1. Decide whether to push this pass's changes (Stage 6 full-population re-run, the
   dark-theme redesign, the em-dash sweep) to the public remote.
2. If publishing: confirm the live dashboard and GitHub Pages reflect the new numbers.
3. Rehearse the 22 interview answers against the updated numbers sheet in
   `docs/resume_and_interview.md`.

**GATE: PASS**
