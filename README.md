# Cedar Support Copilot

An AI support layer for fintech companies. It answers customers **only from the company's own documents**, shows the **source** for every answer, and **hands off to a person** when it isn't confident or when the customer's money is involved. Support agents get a drafted reply to approve.

It's shown on **Cedar Pay**, a fictional money app built as a demo brand.

## Status

| Day | Goal | Status |
|-----|------|--------|
| 1 | Project setup: Django, Postgres + pgvector, data models, admin | ✅ Done |
| 2 | Document upload: chunking, embeddings, injection guard, search API | ✅ Done |
| 3 | Chat API: retrieval, answers with citations, "I don't know" | ⏳ |
| 4 | Human handoff: confidence threshold, ticket queue, drafted replies | ⏳ |
| 5 | Evals: test set, accuracy, citation accuracy, handoff rate | ⏳ |
| 6 | Chat widget and analytics | ⏳ |
| 7 | Deploy, demo video | ⏳ |

## Tech stack

- **Backend:** Django 5 + Django REST Framework
- **Database and vector search:** PostgreSQL 16 with pgvector (HNSW index, cosine distance)
- **AI:** pluggable embeddings (offline by default, any OpenAI-compatible API in production)
- **Testing:** Django tests, eval set, Postman collection

## Project layout

```
config/      settings and URLs
core/        Business and staff accounts, health check
knowledge/   Documents and chunks (embeddings for retrieval)
support/     Conversations, messages, citations, handoff tickets
evals/       Test questions, eval runs and results
```

## Run it locally

Requirements: Python 3.11+, Docker.

```bash
# 1. Start Postgres with pgvector
docker compose up -d

# 2. Install dependencies
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env

# 4. Create the tables and an admin user
python manage.py migrate
python manage.py createsuperuser

# 5. Run
python manage.py runserver
```

Load the Cedar Pay demo (business, a staff login and three sample policy docs):

```bash
python manage.py seed_demo --password choose-a-password
python manage.py ask "How long does a transfer to Spain take?"
```

- Admin: http://127.0.0.1:8000/admin/
- Health check: http://127.0.0.1:8000/api/health/ returns `{"status": "ok", "pgvector": "<version>"}`

## API (so far)

All endpoints need a signed-in staff user (session or `/api-auth/login/`).

| Method | Endpoint | What it does |
|--------|----------|--------------|
| GET | `/api/health/` | App and pgvector status (public) |
| GET / POST | `/api/documents/` | List documents, or add one: `source_type` = `pdf` (multipart `file`), `url` (`source_url`) or `text` (`text`) |
| GET / DELETE | `/api/documents/<id>/` | View or remove a document and its chunks |
| POST | `/api/documents/<id>/reprocess/` | Re-run ingestion (PDF/URL) |
| POST | `/api/search/` | `{"query": "...", "k": 5}` → closest chunks with scores |

## How ingestion works

1. **Extract** text from the PDF, web page or pasted text.
2. **Guard** against prompt injection: lines that read like orders to an AI ("ignore previous instructions…") are removed and listed on the document as `flagged_lines`.
3. **Chunk** by section: each Markdown heading starts a new chunk and stays at its top, with ~200-token chunks and a small overlap inside long sections.
4. **Embed** each chunk (with the document title for context) and store it in pgvector with an HNSW cosine index.

Embeddings are pluggable via `EMBEDDING_PROVIDER`:
- `local` (default): offline hashing embedder, no API key, good for development and tests.
- `openai`: any OpenAI-compatible embeddings API; set `LLM_API_KEY`, `EMBEDDING_MODEL` and, if needed, `LLM_API_BASE`. Run `reprocess` on existing documents after switching.

## Tests

```bash
python manage.py test
```

The tests use the same Postgres database server (Django creates a temporary test database), including a check that vector search returns the nearest chunk.

## Credits

Demo photos on the Cedar Pay home page: Nappy (NappyStock) and Pexels (helloiamtugce, aleksandar069, Sadi Hockmüller).

## Author

Michael Adekunle · [GitHub](https://github.com/Pennymic81) · [LinkedIn](https://linkedin.com/in/michael-adekunle-01776a3b1)
