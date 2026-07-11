# CT-200 QA Test Case Generator

A backend service that ingests the CardioTrack CT-200 device manual as a
browsable section tree, lets a client select sections, and generates
QA test case ideas from that selection using an LLM.

Built for the Tri9T AI (AffineSurge) AI Engineering Internship assignment,
Group A.

## Tech stack

| Concern                         | Choice                          |
|----------------------------------|----------------------------------|
| API layer                        | FastAPI                          |
| Validation / schemas             | Pydantic v2                      |
| Structured/relational data       | SQLAlchemy + SQLite (document tree, selections) |
| Variable-shape data              | TinyDB (LLM-generated test cases) |
| LLM provider                     | Groq (OpenAI-compatible API), with a mock fallback that requires no key |

No deviation from the brief's expected stack was needed.

## Project layout

```
app/
  main.py            FastAPI app, startup seeding
  config.py           Environment variable loading
  database.py          SQLAlchemy engine/session
  models.py            ORM models: DocumentNode, Selection, SelectionNode
  schemas.py            Pydantic request/response models
  parser.py             Markdown -> tree parser
  ingest.py             Shared ingestion routine (seed + upload use this)
  crud.py               DB read/write helpers
  llm.py                 LLM prompt + mock/Groq providers
  nosql.py                TinyDB wrapper for generated test cases
  routers/
    nodes.py               Browse API
    selections.py            Selection API
    generations.py             Generation + retrieval API
    documents.py                Bonus: POST /documents/upload
data/
  ct200_manual.md      Source manual, ingested on startup
tests/
  test_api.py          Pytest end-to-end API suite
  curl_walkthrough.sh   Manual curl walkthrough of every endpoint
```

## Setup

Requires Python 3.10+.

```bash
git clone <your-repo-url>
cd ct200-qa-service
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` works as-is with no changes (LLM_PROVIDER=mock by default). To use
a real LLM, get a free key at https://console.groq.com/keys and set in
`.env`:

```
LLM_PROVIDER=groq
GROQ_API_KEY=your_key_here
```

## Running

```bash
uvicorn app.main:app --reload
```

**Ingestion strategy:** the app ingests `data/ct200_manual.md` automatically
on startup (see `app/main.py`'s `lifespan` handler). No manual step is
needed — the tree is populated the moment the server comes up. This was
chosen over requiring a manual upload call because it means a single
`uvicorn` command gets you a fully working, browsable API, which is the
fastest path for anyone (grader included) to verify the service.

A `POST /documents/upload` endpoint also exists as a bonus, for re-ingesting
a different or updated `.md` file at runtime without restarting the server
(see below).

Once running:
- Interactive API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/

## API reference

### Browse
| Method | Path                | Description                                  |
|--------|----------------------|-----------------------------------------------|
| GET    | `/nodes`               | List top-level sections                       |
| GET    | `/nodes/{id}`           | Get a node with its full body + children      |
| GET    | `/nodes/search?q=...`   | Search node headings/body (substring match)   |

### Selections
| Method | Path                  | Description                          |
|--------|------------------------|----------------------------------------|
| POST   | `/selections`            | Create a selection: `{"node_ids": [1,2], "name": "optional"}` |
| GET    | `/selections/{id}`        | Retrieve a selection with its nodes  |

### Generation & Retrieval
| Method | Path                                | Description                            |
|--------|---------------------------------------|-------------------------------------------|
| POST   | `/selections/{id}/generate`            | Generate 3-5 QA test cases via LLM, persist to TinyDB |
| GET    | `/generations/{generation_id}`          | Fetch one generation by its ID        |
| GET    | `/selections/{id}/generations`           | Fetch all generations for a selection |
| GET    | `/nodes/{id}/generations`                | Fetch all generations touching a node |

### Ingestion (bonus)
| Method | Path                 | Description                                 |
|--------|-----------------------|------------------------------------------------|
| POST   | `/documents/upload`     | Upload a new `.md` file, re-ingests the tree  |

## Testing the API

**Automated tests** (9 end-to-end tests covering ingestion, browse,
selection, generation, retrieval, and error paths):

```bash
pip install pytest
pytest -v
```

**Manual curl walkthrough** (start the server first, in another terminal):

```bash
bash tests/curl_walkthrough.sh
```

Or explore interactively via the Swagger UI at `/docs`.

## Example: end-to-end flow

```bash
# 1. List sections
curl http://127.0.0.1:8000/nodes

# 2. Find the E3 (overpressure) node
curl "http://127.0.0.1:8000/nodes/search?q=E3"

# 3. Create a selection (replace 18 with the real ID from step 2)
curl -X POST http://127.0.0.1:8000/selections \
  -H "Content-Type: application/json" \
  -d '{"node_ids": [18], "name": "overpressure"}'

# 4. Generate test cases (replace 1 with the real selection ID)
curl -X POST http://127.0.0.1:8000/selections/1/generate

# 5. Retrieve them later
curl http://127.0.0.1:8000/selections/1/generations
```

## Notes on the LLM integration

By default `LLM_PROVIDER=mock`, so the project runs and generates
plausible, content-aware test cases with zero external setup or API key —
per the assignment's instruction that a clearly-mocked LLM call is
acceptable if a key isn't available. The mock is keyword-aware (it reads
the selected text for terms like "E3", "overpressure", "battery", etc.)
so it isn't a static fixture; you can verify this by selecting different
sections and seeing the output change.

Setting `LLM_PROVIDER=groq` and providing `GROQ_API_KEY` switches to a
real call against Groq's free-tier API with no other code changes —
`app/llm.py` is the single place this switch happens.

See `APPROACH.md` for the prompt design rationale and data model
explanation.
