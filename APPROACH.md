# Approach Document

## 1. Data model

### Relational store (SQLite via SQLAlchemy)

**`DocumentNode`** — one row per markdown heading (`#`, `##`, or `###`).

| Column        | Purpose                                                      |
|---------------|----------------------------------------------------------------|
| `id`            | Primary key                                                    |
| `heading`        | The heading text                                              |
| `level`           | 1, 2, or 3 — how deep in the hierarchy                        |
| `body`             | Text belonging to this heading, before the next heading of equal-or-shallower depth |
| `order_index`       | Position in the original document, 0-indexed                  |
| `parent_id`           | Self-referential FK; `NULL` for the document root (the `#` title) |

**`Selection`** and **`SelectionNode`** — a `Selection` is a named,
persisted set of node IDs; `SelectionNode` is the many-to-many join table.
It's kept as an explicit model (not SQLAlchemy's `secondary=` shortcut
hiding a plain table) so it's trivial to later add per-row metadata (e.g.
the order a user clicked nodes in) without changing the table's shape.

**Why relational for these two:** both are rigidly structured — a node has
exactly one parent and a fixed set of typed fields; a selection is a
straightforward join. Foreign keys let the database itself guarantee a
selection can't reference a node that doesn't exist, and cascading deletes
keep the tree consistent if a document is re-ingested. This is exactly what
a relational database is for.

### NoSQL store (TinyDB)

Each LLM generation is stored as one JSON document:

```json
{
  "id": "uuid",
  "selection_id": 1,
  "node_ids": [18],
  "model": "llama-3.3-70b-versatile",
  "provider": "groq",
  "generated_at": "2026-07-10T08:20:39Z",
  "test_cases": [
    {"title": "...", "steps": "...", "expected_result": "...", "priority": "high"}
  ]
}
```

**Why NoSQL here:** the *shape* of a generation is not fixed the way a
`DocumentNode` is. The number of test cases varies (3–5), and it's easy to
imagine future fields that don't flatten into columns cleanly — e.g.
multi-step reproduction sequences with per-step expected values, or a
`category` field the LLM decides to add. A rigid SQL table would force
either a lot of nullable columns or a child table per test case just to
hold what is, functionally, "whatever JSON the LLM produced, validated
against a schema." TinyDB stores that directly as a document, which is
also very close to how you'd store it if you swapped in MongoDB later —
migrating this design to real Mongo means changing `app/nosql.py` and
nothing else, since Pydantic (`schemas.GenerationOut`) is enforcing shape
at the API boundary regardless of what's writing to disk.

**Why TinyDB specifically, not Mongo:** it needs zero external services —
just a `pip install`, matching the project's "one command to run" goal.
The tradeoff is real and is worth naming honestly: TinyDB has no real
query language beyond simple predicates, no indexes, and no safe
concurrent writes (it does a full read-modify-write of the JSON file on
every operation). For this assignment's scale (single user, a handful of
generations) that's a non-issue. In production, this is the first thing
I'd swap for MongoDB Atlas's free tier — the interface in `nosql.py`
(`save_generation`, `get_generations_by_selection`, etc.) was written
narrow specifically so that swap touches one file.

## 2. Why the tree is structured this way

The parser (`app/parser.py`) does a single pass with a stack of "currently
open" headings. When it sees a heading of level `L`, it pops the stack
until the top has level `< L` — that becomes the parent. This is the
standard way to turn a flat, depth-marked list into a tree in one pass,
and it naturally handles skipped levels or ragged nesting without special-casing.

One deliberate choice: the document's `#` title becomes a root `DocumentNode`
with `parent_id = NULL`, but it is *not* what `GET /nodes` returns. "Top-level
sections" are defined as the root's direct children (the `##` sections —
"1. Introduction", "2. Device Overview", etc.), because that's what a user
actually means by "sections" — the title itself isn't a section to pick test
cases from. `crud.get_top_level_nodes` encodes this explicitly rather than
hardcoding `level == 2`, so it still works correctly if a future document
has its title one level deeper or shallower.

`order_index` exists because SQL doesn't guarantee row order without an
explicit `ORDER BY`, and `id` order isn't reliable once a document is
re-ingested (old rows deleted, new ones inserted with fresh IDs). Every
list-returning query orders by `order_index`, not `id`.

## 3. LLM prompt design

The prompt (`app/llm.py`) has two parts:

**System prompt** sets the persona and the safety framing explicitly:
*"You are a senior QA engineer at a medical device company... The device
is safety-critical: a missed bug can mean patient harm."* This isn't
decoration — it measurably shifts output toward the kind of test cases the
assignment's own example asks for (concrete, verifiable, safety-aware),
rather than generic "test that it works" filler. It also explicitly
requires that every test case have an unambiguous pass/fail outcome,
matching the assignment's definition of a test case.

**User prompt** does three things:
1. Wraps the reconstructed selection text in clear delimiters, so the
   model doesn't confuse instructions with content.
2. Constrains the model to derive test cases *only* from the given text —
   `"Do not invent behavior the text doesn't support"` — to reduce
   hallucinated thresholds or error codes.
3. Asks for a strict JSON array with a fixed schema and gives one
   format-only example, which makes parsing reliable and keeps the
   response directly mappable to `schemas.TestCase`.

`_extract_json_array` defensively strips markdown code fences and pulls
out the first `[...]` block before parsing, since even well-prompted
models occasionally wrap JSON in prose.

**Reconstruction of selection text** (`crud.collect_selection_text`)
concatenates each selected node's heading and body, in the order the
nodes were selected — so a selection spanning two unrelated sections (say,
3.3 and 5.3) still reads as two clearly-separated, headed blocks rather
than one merged paragraph, which keeps multi-section generations coherent.

## 4. Tradeoffs and what I'd do differently with more time

- **TinyDB's lack of concurrency safety** is the biggest one, discussed
  above — fine for this assignment, first thing to replace for multi-user
  production use.
- **Search is substring-only** (`ILIKE '%term%'`), not full-text search
  with ranking. For a document this small it's sufficient; at real
  document scale I'd move to SQLite FTS5 or a proper search index.
- **No authentication/authorization** — every endpoint is open. Out of
  scope per the brief, but the first thing added before any real
  deployment, especially given the medical-device context.
- **No retry/backoff on the Groq call** — a transient network failure
  currently surfaces as a plain 500. I'd add exponential backoff and a
  clearer error message distinguishing "LLM unreachable" from "LLM
  returned malformed JSON" if this were going further.
- **The mock provider is keyword-based, not a real model** — sufficient to
  demonstrate the pipeline shape end-to-end (it's genuinely aware of what
  was selected, not a static fixture), but it's not a substitute for
  actually exercising the Groq path, which I did verify separately.
- **`order_index` gaps on re-ingestion**: re-uploading a document currently
  wipes and rebuilds the whole tree (including all selections and,
  implicitly, orphaning old generations in TinyDB that reference stale
  node IDs). For a single-document assignment this is acceptable; a
  versioned-document design (keep old trees around, tag selections with a
  document version) would be needed for a system that re-ingests updated
  manuals over time.
