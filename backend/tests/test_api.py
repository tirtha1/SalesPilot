from app.ai import match_customer
from app import main as main_module
from app.models import Customer


def test_list_and_retrieve_customer(client):
    response = client.get("/api/customers")
    assert response.status_code == 200
    assert response.json()[0]["name"] == "ABC Pharma"
    detail = client.get("/api/customers/1")
    assert detail.status_code == 200
    assert detail.json()["contacts"][0]["name"] == "Rahul Sharma"


def test_unknown_customer_returns_consistent_error(client):
    response = client.get("/api/customers/999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_safe_customer_matching_is_ambiguous(db):
    result = match_customer(db, "ABC Pharma")
    assert result.match_status in {"MATCHED", "AMBIGUOUS"}
    fuzzy = match_customer(db, "ABC Pharm")
    assert fuzzy.match_status == "AMBIGUOUS"
    assert len(fuzzy.candidates) >= 1


def test_brief_is_database_grounded(client):
    response = client.get("/api/customers/1/brief")
    assert response.status_code == 200
    body = response.json()
    assert "Delivery reliability" in body["pain_points"]
    assert body["source"] == "local_demo"


def test_analyze_then_confirm_creates_meeting_and_actions(client):
    analysis_response = client.post("/api/meetings/analyze", json={"transcript": "I met Rahul Sharma from ABC Pharma. Please send a revised quotation."})
    assert analysis_response.status_code == 200
    analysis = analysis_response.json()["analysis"]
    confirmation = client.post("/api/meetings/confirm", json={"customer_id": 1, "contact_id": 1, "meeting_date": "2026-09-15T10:00:00Z", "title": "Follow-up", "transcript": "I met Rahul Sharma from ABC Pharma. Please send a revised quotation.", "analysis": analysis})
    assert confirmation.status_code == 201
    assert confirmation.json()["customer_id"] == 1
    assert len(confirmation.json()["action_items"]) >= 1


def test_create_action_item_and_database_ask(client):
    created = client.post("/api/action-items", json={"customer_id": 1, "task": "Share signed quote", "priority": "HIGH"})
    assert created.status_code == 201
    answer = client.post("/api/ai/ask", json={"question": "Which follow-ups are overdue?"})
    assert answer.status_code == 200
    assert "ABC Pharma" in answer.json()["answer"]
    assert answer.json()["source"] == "local_database"


def test_rejects_invalid_audio(client):
    response = client.post("/api/transcription", files={"file": ("notes.txt", b"not audio", "text/plain")})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_AUDIO"


def test_accepts_browser_audio_codec_mime_type(client, monkeypatch):
    monkeypatch.setattr(main_module, "transcribe_audio", lambda filename, mime_type, content: "captured transcript")
    response = client.post("/api/transcription", files={"file": ("recording.webm", b"audio", "audio/webm;codecs=opus")})
    assert response.status_code == 200
    assert response.json()["transcript"] == "captured transcript"
