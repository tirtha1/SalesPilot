# SalesPilot REST API

Interactive contracts and schemas are available at `GET /docs`. All errors use `{"error":{"code":"...","message":"...","request_id":"..."}}` and all IDs are integers.

| Endpoint | Method | Body / query | Success | Common errors |
|---|---|---|---|---|
| `/health` | GET | — | service status | 500 |
| `/api/dashboard` | GET | — | dashboard cards | 500 |
| `/api/customers` | GET | `?search=` | customer summaries | 500 |
| `/api/customers/{id}` | GET | — | customer + contacts | `NOT_FOUND` |
| `/api/customers/{id}/history` | GET | — | meetings, opportunities, actions | `NOT_FOUND` |
| `/api/customers/{id}/brief` | GET | — | database-grounded AI brief | `NOT_FOUND`, `AI_ANALYSIS_FAILED` |
| `/api/ai/brief/{id}` | POST | — | same brief response | `NOT_FOUND` |
| `/api/meetings` | GET | `?customer_id=&limit=` | meeting list | `INVALID_REQUEST` |
| `/api/meetings/{id}` | GET | — | meeting detail | `NOT_FOUND` |
| `/api/meetings` | POST | `MeetingCreate` | created meeting | `INVALID_REQUEST` |
| `/api/meetings/analyze` | POST | transcript + optional meeting date | analysis draft + safe customer match | `AI_ANALYSIS_FAILED` |
| `/api/ai/analyze-meeting` | POST | same as analyze | analysis draft | `AI_ANALYSIS_FAILED` |
| `/api/meetings/confirm` | POST | reviewed `MeetingConfirmRequest` | saved meeting + actions | `NOT_FOUND`, `INVALID_REQUEST` |
| `/api/meetings/{id}/confirm` | POST | reviewed draft | compatibility confirmation route | `NOT_FOUND` |
| `/api/transcription` | POST | multipart `file` | transcript | `INVALID_AUDIO`, `AUDIO_TOO_LARGE`, `TRANSCRIPTION_FAILED` |
| `/api/ai/ask` | POST | question | grounded answer + citations | `AI_QUERY_FAILED` |
| `/api/action-items` | GET | `?status=` | action items | 500 |
| `/api/action-items/today` | GET | — | open actions due today | 500 |
| `/api/action-items/overdue` | GET | — | overdue open actions | 500 |
| `/api/action-items` | POST | `ActionItemCreate` | created action | `NOT_FOUND`, `INVALID_REQUEST` |
| `/api/action-items/{id}` | PATCH | `ActionItemPatch` | updated action | `NOT_FOUND` |
| `/api/opportunities` | GET | `?customer_id=` | opportunities | 500 |
| `/api/opportunities/{id}` | GET | — | opportunity | `NOT_FOUND` |
| `/api/opportunities/{id}` | PATCH | `OpportunityPatch` | updated opportunity | `NOT_FOUND`, `INVALID_REQUEST` |

## Primary request examples

### Analyze a meeting (draft only)

```bash
curl -X POST http://localhost:8000/api/meetings/analyze \
  -H "Content-Type: application/json" \
  -d '{"transcript":"I met Rahul at ABC Pharma. Send a revised quotation by Friday."}'
```

Response fields: `analysis.customer_name`, `analysis.summary`, extraction arrays, `action_items`, `follow_up`, `confidence`, and a `match` object. `AMBIGUOUS` matches include candidates and must not be auto-saved.

### Confirm a reviewed meeting

```bash
curl -X POST http://localhost:8000/api/meetings/confirm \
  -H "Content-Type: application/json" \
  -d '{"customer_id":1,"contact_id":1,"meeting_date":"2026-09-15T10:00:00Z","title":"ABC Pharma review","transcript":"...","analysis":{"summary":"Discussed a quotation.","requirements":[],"pain_points":[],"customer_concerns":[],"competitors":[],"opportunities":[],"action_items":[{"task":"Send quotation","due_date":null,"priority":"HIGH"}],"follow_up":{"required":true,"date":null,"clarification_needed":true},"confidence":{"customer":1,"contact":1,"overall":.8}}}'
```

### Ask SalesPilot

```bash
curl -X POST http://localhost:8000/api/ai/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Which customers should I follow up with today?"}'
```

Response: `{"answer":"...","citations":[{"customer_name":"ABC Pharma","record_type":"ACTION_ITEM","detail":"Send quotation"}],"source":"openai_tools"}`. A missing fact is reported as unavailable, never fabricated.

### Upload audio

```bash
curl -X POST http://localhost:8000/api/transcription -F "file=@meeting.webm;type=audio/webm"
```

Returns `{"transcript":"...","source":"openai"}`. It accepts WebM, MP3, MP4/M4A, OGG, WAV, FLAC, MPEG/MPGA up to 25 MB.

The OpenAPI document supplies complete Pydantic field constraints, status codes, response bodies, and examples for all routes.
