# SalesPilot

An AI-assisted, human-in-the-loop sales workspace for preparing customer briefs, recording meeting notes, extracting structured follow-ups, and querying CRM facts safely.

## Quick start (Windows PowerShell)

Prerequisites: Python 3.12+, Node.js 20+, Docker Desktop.

```powershell
Copy-Item .env.example .env
docker compose up -d postgres
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
Set-Location backend
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open `http://localhost:5173`; API docs are at `http://localhost:8000/docs`.

`OPENAI_API_KEY` is optional for the seed-data demo. Without it, SalesPilot uses a clearly-labelled deterministic local extractor and database-grounded query fallback. Add a backend-only key to enable OpenAI Responses API tool calls, structured extraction, and transcription.

## Commands

```powershell
# Backend tests (from repository root, venv active)
$env:DATABASE_URL = "sqlite+pysqlite:///./test.db"
pytest backend/tests -q

# Build the frontend
Set-Location frontend; npm run build
```

## Safety notes

- The browser never receives `OPENAI_API_KEY`.
- Meeting analysis is a draft only; `Confirm & Save` is the only database write path for AI-derived content.
- Model tools are allow-listed server functions with Pydantic validation. There is no model-supplied SQL path.
- The transcription endpoint limits size and accepts only supported audio MIME types.

See [architecture](docs/ARCHITECTURE.md) and [API reference](docs/API.md).

