# Implementation log

Running record of what we did, why, and what came out of it. Plan: [module-requirements/implementation-plan.md](module-requirements/implementation-plan.md).

**Rule:** at the end of every phase, add one entry (template below) before moving on. Keep entries short and put real output in them: counts, plans, test results.

## Entry template

```markdown
### Phase N — title (YYYY-MM-DD)

**Goal:** one line.
**What we did:** 3–6 bullets, in order. Name files/commits.
**How we decided:** the question, the evidence (query, data profile, EXPLAIN), the alternatives rejected.
**Outcome:** what works now, with numbers or pasted output.
**Problems / changes to plan:** what broke or surprised us; what we changed.
**Report/demo material:** which output to reuse (EXPLAIN, ERD, test run, counts).
```

---

## Decision evidence (how we got to each reason)

Each decision in the plan came from a check on the real data or code, not from preference. Fill the "Outcome" column when the phase is done.

| Decision | How we got there (evidence) | Rejected alternative | Outcome |
| --- | --- | --- | --- |
| D1 Merge 15 layer tables into points + areas | Live models are the same shape: `source_id, name, <type col>, catalog_id, district_id, attrs, geom`; only the type column name differs ([models.py](../backend/app/models.py)). | Keep one table per layer. | pending |
| D3 Many-to-many via tags | Profiled cached WFS: EV `anschluss_1..4` gives 7 connector types, 247 chargers with more than one; Kita `ang_1` gives 9 approaches, 950 of 2,905 kitas with more than one. Values like `A/B` break 1NF. | Dedicated junction per kind (needs one table pair per kind). | pending |
| D4 Upsert on `(kind_code, source_id)` | Checked source key per layer: unique and non-null except toilets (525 null) and bike parking (19 duplicate `projektnummer`). Current import deletes and reinserts everything. | Delete and reinsert (new ids every run). | pending |
| D6 `tree_species` lookup | `art_bot → art_dtsch, gattung` had 0 conflicts across street (719 species) and park (835) trees. | Keep species text on every tree row. | pending |
| D7 `operator` table | `t_nr → t_name, t_art` had 0 conflicts over 1,165 kita operators; EV `betreiber` has 203 names. | Operator name copied onto features. | pending |
| D8 Partition by kind | Trees are about 962k of about 981k point rows (counted from cache files). | Separate tree tables; one big table. | pending |
| 0 → NULL for tree sizes | `baumhoehe` is 0 or missing for about 69k street and 95k park trees. | Store 0. | pending |
| D11 Read-only role | [sql.py](../backend/app/routers/sql.py) relies on a SELECT check plus `statement_timeout`; no database privilege limit. | Python check only. | pending |

---

## Entries

### Phase pre-0 — Design and planning (2026-11-05)

**Goal:** agree a schema and plan that satisfies the module hand-in.
**What we did:**
- Read the module requirements, the live code and schema v2 docs.
- Found the gap: no many-to-many relationship in the live or v2 schema.
- Profiled cached WFS data for multi-valued fields, key uniqueness and operator/species dependencies (results in the table above).
- Wrote the Mermaid ERD, updated `schema.sql`, and wrote [project-plan.md](project-plan.md) and the implementation plan.
**How we decided:** see the evidence table.
**Outcome:** design docs and plan committed to the working tree (not yet to git). Nothing in the database has changed.
**Problems / changes to plan:** the database was not running (Docker down), so row counts come from cache files and `schema.sql` has not been applied yet.
**Report/demo material:** ERD, data volume table in project-plan.
