# Study guide: schema v2 (4 hours, beginner friendly)

This guide tells you what to read, in what order, and what you should be able to say afterwards. You do not need to know databases well to start.

## The story in one minute

The map app shows Berlin amenities: schools, toilets, EV chargers, parks, trees and more. The data comes from 15 open-data layers.

**Before (v1):** one table per layer. The 15 tables had almost the same columns, so we repeated ourselves, and every analysis had to list all of them by hand. There was also no many-to-many relationship, which the module hand-in requires.

**After (v2):** we designed the database first, then loaded the data into it.

1. **Merge 15 tables into 2.** `amenity_points` (things that are a dot on the map) and `amenity_areas` (things that are a shape, like parks). A `kind` column says whether a row is a school, a toilet, and so on.
2. **Add a many-to-many relationship.** An EV charger can have several connector types, and one connector type fits many chargers. A third table in the middle, `amenity_point_tag`, links the two sides.
3. **Move repeated facts into their own tables.** Operators, tree species and per-kind details (tree size, Kita capacity) each get a table.

## Words you will meet

| Word | Plain meaning |
|---|---|
| Table | A spreadsheet-like list of rows with fixed columns |
| Primary key (PK) | The column(s) that identify one row uniquely |
| Foreign key (FK) | A column that points at a row in another table, so the database refuses a pointer to nothing |
| Constraint | A rule the database enforces itself (unique, not null, a CHECK on a value) |
| One-to-many | One district has many features |
| Many-to-many | Many chargers have many connector types; needs a junction table |
| Junction table | The table in the middle of a many-to-many; each row is one link |
| Normalization | Organizing tables so each fact is stored once (1NF, 2NF, 3NF are its steps) |
| Index | A lookup shortcut that makes queries faster at some cost on writes |
| EXPLAIN | Asks Postgres how it plans to run a query, so you can see whether an index is used |
| Partition | Splitting one big table into pieces by a column, so a query can skip pieces it does not need |
| Transaction / ACID | A group of changes that all succeed or all roll back |
| Upsert | Insert a row, or update it if it already exists |
| Migration | A versioned script that changes the database structure (we use Alembic) |
| Materialized view | A saved query result, stored like a table, refreshed on demand |

## The reading plan (about 4 hours)

### 1. The ER diagram: 30 min
File: [schema-v2/erd.md](schema-v2/erd.md)

This is the whole model in one picture. Do not try to memorize it; find these:

- the two big tables, `amenity_points` and `amenity_areas`
- the many-to-many: `amenity_point_tag` between points and tags
- the 1:1 detail tables: `tree_detail`, `kita_detail`, `ev_charger_detail`
- the small lookups: `operator`, `tree_species`, `districts`

**Check yourself:** close the file and redraw the picture on paper. Boxes and lines are enough.

### 2. Normalization: 45 min
File: [schema-v2/normalization.md](schema-v2/normalization.md)

Normalization means "store each fact once". The three steps, with our own examples:

- **1NF:** one value per cell. v1 stored `'AC Typ 2; DC CCS'` in one text cell, which breaks it. v2 uses one tag row per connector.
- **2NF:** every column depends on the whole key, not part of it.
- **3NF:** columns depend on the key and nothing else. Example: a tree's German name and genus follow from its botanical name, so they live in `tree_species`, not on 962k tree rows.

**Check yourself:** explain 3NF using `tree_species`.

### 3. Design decisions: 60 min
File: [schema-v2/design-decisions.md](schema-v2/design-decisions.md)

Each entry (D1 to D12) has a decision, the alternatives we rejected, evidence, and the cost we accept. An assessor will ask "why this and not that?", and this file is your answer sheet. Read all of it, but know these four well:

- **D1:** why two tables instead of fifteen
- **D3:** why a junction table, and not a text column, an array, or key/value rows
- **D5:** why tree, Kita and charger facts live in separate 1:1 tables
- **D8:** why `amenity_points` is partitioned by kind (16.6 ms against 79.2 ms on one flat table)

**Check yourself:** for each of the four, say the decision, one rejected alternative and one number.

### 4. The real SQL: 45 min
File: [schema-v2/schema.sql](schema-v2/schema.sql)

Keep the ER diagram open next to it. You are matching boxes to `CREATE TABLE` statements. Trace two things:

1. The many-to-many: find `amenity_point_tag` and see which foreign keys it has.
2. One rule that the database enforces. For example, `amenity_kind` has `UNIQUE (code, geom_family)` and the feature tables point at it, so a polygon kind cannot be put in the points table.

### 5. Speed and safety: 30 min
Files: [schema-v2/indexing-and-explain.md](schema-v2/indexing-and-explain.md) and [schema-v2/acid-and-transactions.md](schema-v2/acid-and-transactions.md)

Two topics that usually come up in the oral demo.

- **Indexing:** what an index is and how EXPLAIN shows it being used. The measured plans are in `schema-v2/explain/`.
- **ACID:** each layer import runs in one transaction. If it fails halfway, nothing is half-written.

### 6. War stories: 30 min
File: [implementation-log.md](implementation-log.md). Read only the "Problems / changes to plan" bullets.

Real stories make good demo answers. Two good ones:

- **The `0.04` bug (phase 2):** a tree crown diameter of `0.04` rounds to `0.0`, which breaks a `CHECK (> 0)` rule. The import rolled back after 15 minutes. The database caught a bug our own code missed.
- **The district assignment (phase 2):** three attempts. The first was still running after 8 minutes, and the real cost turned out to be rewriting 434k rows after insert, so we compute it before writing.

### 7. Watch the database say no: about 20 min
File: `backend/tests/test_constraints.py`

Run it and read a few of the tests. Each one tries to insert bad data and checks that the database refuses it with the right constraint. This is the best thing to show in a live demo.

## How we built it (for context)

Ten phases on the branch `feat/schema-v2`, each one commit plus one log entry:

| Phase | What happened |
|---|---|
| 0 | Wrote the design docs and the SQL; tested it on a scratch database |
| 1 | Alembic migration `0009_schema_v2` and constraint tests |
| 2 | New importer (`import_v2.py`): 980k features loaded; a repeat import changes 0 rows |
| 3 | ORM models and a read-only database role for the SQL playground |
| 4 | API and analyses ported to the new tables; tag filter and operator report added |
| 5 | Frontend updated: tag chips, feature card, new Compare measures |
| 6 | Cutover: old tables and old importer removed |
| 7 | EXPLAIN evidence and a materialized view |
| 8 | WAL archiving, backup and point-in-time recovery drill |
| 9 | README, project plan and demo script |

## Final check

You are ready when you can, without notes:

1. Redraw the ER diagram.
2. Explain why `amenity_point_tag` exists.
3. Explain 1NF, 2NF and 3NF with one v2 example each.
4. Give the decision, the rejected alternative and one number for D1, D3, D5 and D8.
5. Show one constraint refusing bad data.
