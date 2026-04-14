import base64
import json
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request, Response, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import anthropic

from db import (
    init_db, create_document, get_document, get_all_documents,
    get_documents_for_user, get_stage_outputs, save_stage_output,
    update_document_stage, log_audit, get_audit_log,
)
from agents import (
    load_glossary, translation_agent, editing_agent, typesetting_agent,
    get_available_models, DEFAULT_MODEL,
)

app = FastAPI(title="Bahai Chinese Translation Workbench — Phase 3")

GLOSSARY = []
TEAM = []
PIPELINE_SETTINGS = {}  # {stage_number: model_key}
PROJECT_DIR = Path(__file__).parent
SETTINGS_PATH = PROJECT_DIR / "pipeline_settings.json"


@app.on_event("startup")
def startup():
    init_db()
    _load_glossary()
    _load_team()
    _load_pipeline_settings()


def _load_glossary():
    global GLOSSARY
    path = PROJECT_DIR / "glossary.json"
    if path.exists():
        GLOSSARY = load_glossary(str(path))

def _save_glossary():
    with open(PROJECT_DIR / "glossary.json", "w", encoding="utf-8") as f:
        json.dump(GLOSSARY, f, ensure_ascii=False, indent=4)

def _load_team():
    global TEAM
    path = PROJECT_DIR / "team.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            TEAM = json.load(f)

def _save_team():
    with open(PROJECT_DIR / "team.json", "w", encoding="utf-8") as f:
        json.dump(TEAM, f, ensure_ascii=False, indent=4)

def _load_pipeline_settings():
    global PIPELINE_SETTINGS
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, "r") as f:
            PIPELINE_SETTINGS = json.load(f)
    else:
        PIPELINE_SETTINGS = {"1": DEFAULT_MODEL, "3": DEFAULT_MODEL, "4": DEFAULT_MODEL}
        _save_pipeline_settings()

def _save_pipeline_settings():
    with open(SETTINGS_PATH, "w") as f:
        json.dump(PIPELINE_SETTINGS, f, indent=2)


_load_glossary()
_load_team()
_load_pipeline_settings()


# ---------------------------------------------------------------------------
# API key helper (demo mode: user supplies their own Anthropic key)
# ---------------------------------------------------------------------------

def _require_api_key(x_api_key):
    if not x_api_key or not x_api_key.strip():
        raise HTTPException(
            status_code=401,
            detail="Anthropic API key required. Please enter your key in the API Key panel at the top of the app. Get a free key at console.anthropic.com.",
        )
    return x_api_key.strip()


def _handle_anthropic_errors(exc):
    """Translate Anthropic SDK errors into HTTPException with friendly messages."""
    if isinstance(exc, anthropic.AuthenticationError):
        raise HTTPException(status_code=401, detail="Invalid Anthropic API key. Please check your key and try again.")
    if isinstance(exc, anthropic.RateLimitError):
        raise HTTPException(status_code=429, detail="Your Anthropic account rate limit was hit. Please wait a moment and try again.")
    if isinstance(exc, anthropic.APIError):
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {str(exc)}")
    raise exc


# ---------------------------------------------------------------------------
# Auth helpers (same as Phase 2)
# ---------------------------------------------------------------------------

COOKIE_NAME = "workbench_user_p3"

def _encode_cookie(name, role):
    return base64.b64encode(f"{name}|{role}".encode("utf-8")).decode("ascii")

def _decode_cookie(value):
    try:
        parts = base64.b64decode(value.encode("ascii")).decode("utf-8").split("|", 1)
        return {"name": parts[0], "role": parts[1]} if len(parts) == 2 else None
    except Exception:
        return None

def _get_current_user(request: Request):
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie: return None
    user = _decode_cookie(cookie)
    if not user: return None
    member = next((m for m in TEAM if m["name"] == user["name"]), None)
    return {"name": member["name"], "role": member["role"]} if member else None

def _require_user(request: Request):
    user = _get_current_user(request)
    if not user: raise HTTPException(status_code=401, detail="Not logged in")
    return user

def _require_role(request: Request, allowed_roles: list):
    user = _require_user(request)
    if user["role"] not in allowed_roles: raise HTTPException(status_code=403, detail="Permission denied")
    return user


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    name: str
    role: str

class CreateDocumentRequest(BaseModel):
    title: str
    source_text: str
    source_lang: str = "en"
    governor_model: str = "single"
    governor_a: str | None = None
    governor_b: str | None = None

class ReviewRequest(BaseModel):
    decision: str
    edited_text: str | None = None
    notes: str | None = None
    accuracy_rating: str | None = None
    accuracy_notes: str | None = None
    beauty_rating: str | None = None
    beauty_notes: str | None = None
    consistency_rating: str | None = None
    consistency_notes: str | None = None

class ProofreadRequest(BaseModel):
    decision: str
    edited_text: str | None = None
    notes: str | None = None

class TeamMemberRequest(BaseModel):
    name: str
    role: str

class GlossaryTermRequest(BaseModel):
    english: str
    chinese: str
    notes: str = ""
    category: str = "concept"

class PipelineSettingsRequest(BaseModel):
    stage_1: str = DEFAULT_MODEL
    stage_3: str = DEFAULT_MODEL
    stage_4: str = DEFAULT_MODEL

class StageOutput(BaseModel):
    stage: int
    input_text: str
    output_text: str
    operator: str
    model_used: str | None = None
    human_notes: str | None = None
    created_at: str

class DocumentDetailResponse(BaseModel):
    id: int
    title: str
    source_text: str
    source_lang: str
    current_stage: int
    status: str
    governor_model: str = "single"
    governor_a: str | None = None
    governor_b: str | None = None
    stages: list[StageOutput]
    audit: list[dict] = []

class DocumentListItem(BaseModel):
    id: int
    title: str
    source_lang: str
    current_stage: int
    status: str
    governor_model: str = "single"
    governor_a: str | None = None
    governor_b: str | None = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_clean_text(raw):
    """Keep unwrapping JSON and markdown fences until we get plain text."""
    import re
    text = raw
    for _ in range(5):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
        text = re.sub(r"\n?```\s*$", "", text.strip())
        if text.strip().startswith("{"):
            try:
                data = json.loads(text)
                extracted = data.get("typeset_text") or data.get("edited_text") or data.get("translation")
                if extracted:
                    text = extracted
                    continue
                else:
                    break
            except (json.JSONDecodeError, TypeError):
                break
        else:
            break
    return text

def _build_response(doc_id):
    doc = get_document(doc_id)
    if doc is None: raise HTTPException(status_code=404, detail="Document not found")
    stages = get_stage_outputs(doc_id)
    audit = get_audit_log(doc_id)
    return DocumentDetailResponse(
        id=doc["id"], title=doc["title"], source_text=doc["source_text"],
        source_lang=doc["source_lang"], current_stage=doc["current_stage"],
        status=doc["status"], governor_model=doc.get("governor_model", "single"),
        governor_a=doc.get("governor_a"), governor_b=doc.get("governor_b"),
        stages=[StageOutput(stage=s["stage"], input_text=s["input_text"], output_text=s["output_text"],
                            operator=s["operator"], model_used=s.get("model_used"),
                            human_notes=s.get("human_notes"), created_at=s["created_at"]) for s in stages],
        audit=audit,
    )


# ---------------------------------------------------------------------------
# Routes: UI + Health
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    return HTMLResponse(content=(PROJECT_DIR / "index.html").read_text(encoding="utf-8"))

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Routes: Auth
# ---------------------------------------------------------------------------

@app.post("/api/login")
def login(req: LoginRequest, response: Response):
    member = next((m for m in TEAM if m["name"] == req.name), None)
    if not member: raise HTTPException(status_code=401, detail="Name not found. Please contact your coordinator.")
    if member["role"] != req.role: raise HTTPException(status_code=401, detail=f"Your registered role is '{member['role']}', not '{req.role}'.")
    response.set_cookie(key=COOKIE_NAME, value=_encode_cookie(member["name"], member["role"]), httponly=False, samesite="lax", max_age=86400*30)
    return {"name": member["name"], "role": member["role"]}

@app.get("/api/me")
def get_me(request: Request):
    user = _get_current_user(request)
    if not user: raise HTTPException(status_code=401, detail="Not logged in")
    return user

@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Routes: Pipeline Settings + Models (Phase 3)
# ---------------------------------------------------------------------------

@app.get("/api/models")
def list_models():
    return {"models": get_available_models(), "demo_mode": True, "enabled_providers": ["anthropic"]}

@app.get("/api/pipeline-settings")
def get_pipeline_settings(request: Request):
    _require_role(request, ["coordinator"])
    return {"settings": PIPELINE_SETTINGS, "models": get_available_models(), "demo_mode": True}

@app.post("/api/pipeline-settings")
def update_pipeline_settings(req: PipelineSettingsRequest, request: Request):
    _require_role(request, ["coordinator"])
    # Demo mode: only Claude is allowed across all stages
    for stage, model in [("stage_1", req.stage_1), ("stage_3", req.stage_3), ("stage_4", req.stage_4)]:
        if model != "claude":
            raise HTTPException(status_code=400, detail=f"Demo mode: only Claude is supported. {stage} must be set to 'claude'.")
    global PIPELINE_SETTINGS
    PIPELINE_SETTINGS = {"1": req.stage_1, "3": req.stage_3, "4": req.stage_4}
    _save_pipeline_settings()
    return {"settings": PIPELINE_SETTINGS}

@app.get("/api/dashboard")
def get_dashboard(request: Request):
    _require_user(request)
    docs = get_all_documents()
    stage_names = {1: "Translation", 2: "Review", 3: "Editing", 4: "Typesetting", 5: "Proofread"}
    summary = {"total": len(docs), "completed": 0, "in_progress": 0, "by_stage": {1:0,2:0,3:0,4:0,5:0}}
    for d in docs:
        if d["status"] == "completed":
            summary["completed"] += 1
        else:
            summary["in_progress"] += 1
            s = d["current_stage"]
            if s in summary["by_stage"]:
                summary["by_stage"][s] += 1
    summary["stage_names"] = stage_names
    summary["pipeline_settings"] = PIPELINE_SETTINGS
    summary["models"] = {k: v["label"] for k, v in __import__("agents").AVAILABLE_MODELS.items()}
    return summary


# ---------------------------------------------------------------------------
# Routes: Team
# ---------------------------------------------------------------------------

@app.get("/api/team")
def get_team(request: Request):
    _require_role(request, ["coordinator"])
    return {"members": TEAM}

@app.post("/api/team")
def add_team_member(req: TeamMemberRequest, request: Request):
    _require_role(request, ["coordinator"])
    if next((m for m in TEAM if m["name"] == req.name), None): raise HTTPException(status_code=400, detail="Member already exists")
    TEAM.append({"name": req.name, "role": req.role})
    _save_team()
    return {"members": TEAM}

@app.delete("/api/team/{name}")
def remove_team_member(name: str, request: Request):
    _require_role(request, ["coordinator"])
    global TEAM
    before = len(TEAM)
    TEAM = [m for m in TEAM if m["name"] != name]
    if len(TEAM) == before: raise HTTPException(status_code=404, detail="Member not found")
    _save_team(); _load_team()
    return {"members": TEAM}


# ---------------------------------------------------------------------------
# Routes: Glossary
# ---------------------------------------------------------------------------

@app.get("/api/glossary")
def get_glossary():
    return {"terms": GLOSSARY}

@app.post("/api/glossary")
def add_or_update_glossary_term(req: GlossaryTermRequest, request: Request):
    _require_role(request, ["coordinator", "terminology_specialist"])
    global GLOSSARY
    existing = next((t for t in GLOSSARY if t["english"] == req.english), None)
    if existing: existing.update({"chinese": req.chinese, "notes": req.notes, "category": req.category})
    else: GLOSSARY.append({"english": req.english, "chinese": req.chinese, "notes": req.notes, "category": req.category})
    _save_glossary()
    return {"terms": GLOSSARY}

@app.delete("/api/glossary/{english}")
def delete_glossary_term(english: str, request: Request):
    _require_role(request, ["coordinator", "terminology_specialist"])
    global GLOSSARY
    before = len(GLOSSARY)
    GLOSSARY = [t for t in GLOSSARY if t["english"] != english]
    if len(GLOSSARY) == before: raise HTTPException(status_code=404, detail="Term not found")
    _save_glossary()
    return {"terms": GLOSSARY}


# ---------------------------------------------------------------------------
# Routes: Documents (with multi-LLM)
# ---------------------------------------------------------------------------

@app.get("/api/documents")
def list_documents(request: Request):
    user = _require_user(request)
    docs = get_documents_for_user(user["name"], user["role"])
    return {"documents": [DocumentListItem(
        id=d["id"], title=d["title"], source_lang=d["source_lang"],
        current_stage=d["current_stage"], status=d["status"],
        governor_model=d.get("governor_model","single"),
        governor_a=d.get("governor_a"), governor_b=d.get("governor_b"),
        created_at=d["created_at"], updated_at=d["updated_at"],
    ) for d in docs]}

@app.post("/api/documents")
def create_doc(req: CreateDocumentRequest, request: Request,
               x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    _require_role(request, ["coordinator"])
    api_key = _require_api_key(x_api_key)
    doc_id = create_document(req.title, req.source_text, req.source_lang, req.governor_model, req.governor_a, req.governor_b)
    log_audit(doc_id, "stage1_started")
    model_key = PIPELINE_SETTINGS.get("1", DEFAULT_MODEL)
    try:
        result = translation_agent(req.source_text, req.source_lang, GLOSSARY, model_key=model_key, api_key=api_key)
    except (anthropic.AuthenticationError, anthropic.RateLimitError, anthropic.APIError) as e:
        _handle_anthropic_errors(e)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_stage_output(doc_id=doc_id, stage=1, input_text=req.source_text, output_text=result["translation"],
                      operator="ai", model_used=result.get("model_used"), prompt_used=result.get("prompt_used"))
    log_audit(doc_id, "stage1_completed", {"term_usage": result.get("term_usage",[]), "notes": result.get("notes",""), "model": model_key})
    update_document_stage(doc_id, 2)
    return _build_response(doc_id)

@app.get("/api/documents/{doc_id}")
def get_doc(doc_id: int, request: Request):
    _require_user(request)
    return _build_response(doc_id)

@app.post("/api/documents/{doc_id}/review")
def review_doc(doc_id: int, req: ReviewRequest, request: Request):
    user = _require_user(request)
    doc = get_document(doc_id)
    if not doc: raise HTTPException(status_code=404, detail="Document not found")
    if doc["current_stage"] != 2: raise HTTPException(status_code=400, detail="Document is not at Stage 2")
    stages = get_stage_outputs(doc_id)
    s1 = next((s for s in stages if s["stage"]==1), None)
    if not s1: raise HTTPException(status_code=400, detail="Stage 1 output not found")
    human_notes = json.dumps({"reviewer": user["name"], "notes": req.notes, "checklist": {
        "accuracy": {"rating": req.accuracy_rating, "notes": req.accuracy_notes},
        "beauty": {"rating": req.beauty_rating, "notes": req.beauty_notes},
        "consistency": {"rating": req.consistency_rating, "notes": req.consistency_notes},
    }}, ensure_ascii=False) if any([req.accuracy_rating, req.beauty_rating, req.consistency_rating]) else req.notes

    if req.decision == "approve":
        save_stage_output(doc_id=doc_id, stage=2, input_text=s1["output_text"], output_text=s1["output_text"], operator="human", human_notes=human_notes)
        log_audit(doc_id, "stage2_approved", {"reviewer": user["name"]}); update_document_stage(doc_id, 3)
    elif req.decision == "edit":
        if not req.edited_text: raise HTTPException(status_code=400, detail="edited_text required")
        save_stage_output(doc_id=doc_id, stage=2, input_text=s1["output_text"], output_text=req.edited_text, operator="human", human_notes=human_notes)
        log_audit(doc_id, "stage2_edited", {"reviewer": user["name"]}); update_document_stage(doc_id, 3)
    elif req.decision == "reject":
        log_audit(doc_id, "stage2_rejected", {"reviewer": user["name"], "notes": req.notes})
    else: raise HTTPException(status_code=400, detail="Invalid decision")
    return _build_response(doc_id)

@app.post("/api/documents/{doc_id}/edit")
def edit_doc(doc_id: int, request: Request,
             x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    _require_user(request)
    api_key = _require_api_key(x_api_key)
    doc = get_document(doc_id)
    if not doc: raise HTTPException(status_code=404, detail="Document not found")
    if doc["current_stage"] != 3: raise HTTPException(status_code=400, detail="Document is not at Stage 3")
    stages = get_stage_outputs(doc_id)
    s2 = next((s for s in stages if s["stage"]==2), None)
    if not s2: raise HTTPException(status_code=400, detail="Stage 2 output not found")

    # Stage 3: Editing
    log_audit(doc_id, "stage3_started")
    model_3 = PIPELINE_SETTINGS.get("3", DEFAULT_MODEL)
    try:
        edit_result = editing_agent(doc["source_text"], s2["output_text"], GLOSSARY, model_key=model_3, api_key=api_key)
    except (anthropic.AuthenticationError, anthropic.RateLimitError, anthropic.APIError) as e:
        _handle_anthropic_errors(e)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_stage_output(doc_id=doc_id, stage=3, input_text=s2["output_text"],
                      output_text=json.dumps({"edited_text": edit_result["edited_text"], "changes_made": edit_result.get("changes_made",[]), "checklist": edit_result.get("checklist",{})}, ensure_ascii=False),
                      operator="ai", model_used=edit_result.get("model_used"), prompt_used=edit_result.get("prompt_used"))
    log_audit(doc_id, "stage3_completed", {"model": model_3})

    # Stage 4: Typesetting
    log_audit(doc_id, "stage4_started")
    model_4 = PIPELINE_SETTINGS.get("4", DEFAULT_MODEL)
    try:
        ts_result = typesetting_agent(doc["source_text"], edit_result["edited_text"], GLOSSARY, model_key=model_4, api_key=api_key)
    except (anthropic.AuthenticationError, anthropic.RateLimitError, anthropic.APIError) as e:
        _handle_anthropic_errors(e)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_stage_output(doc_id=doc_id, stage=4, input_text=edit_result["edited_text"],
                      output_text=json.dumps({"typeset_text": ts_result["typeset_text"], "issues_found": ts_result.get("issues_found",[]), "validation_checklist": ts_result.get("validation_checklist",{})}, ensure_ascii=False),
                      operator="ai", model_used=ts_result.get("model_used"), prompt_used=ts_result.get("prompt_used"))
    log_audit(doc_id, "stage4_completed", {"model": model_4})
    update_document_stage(doc_id, 5)
    return _build_response(doc_id)

@app.post("/api/documents/{doc_id}/proofread")
def proofread_doc(doc_id: int, req: ProofreadRequest, request: Request):
    user = _require_user(request)
    doc = get_document(doc_id)
    if not doc: raise HTTPException(status_code=404, detail="Document not found")
    if doc["current_stage"] != 5: raise HTTPException(status_code=400, detail="Document is not at Stage 5")
    gov_model = doc.get("governor_model", "single")
    if gov_model == "single" and doc.get("governor_a") and user["name"] != doc["governor_a"] and user["role"] != "coordinator":
        raise HTTPException(status_code=403, detail="Only Governor A can proofread")
    elif gov_model == "dual" and doc.get("governor_b") and user["name"] != doc["governor_b"] and user["role"] != "coordinator":
        raise HTTPException(status_code=403, detail="Only Governor B can proofread")
    stages = get_stage_outputs(doc_id)
    s4 = next((s for s in stages if s["stage"]==4), None)
    if not s4: raise HTTPException(status_code=400, detail="Stage 4 output not found")
    typeset_text = _extract_clean_text(s4["output_text"])

    if req.decision == "approve":
        save_stage_output(doc_id=doc_id, stage=5, input_text=typeset_text, output_text=typeset_text, operator="human",
                          human_notes=json.dumps({"reviewer": user["name"], "notes": req.notes}, ensure_ascii=False))
        log_audit(doc_id, "stage5_approved", {"reviewer": user["name"]}); update_document_stage(doc_id, 5, status="completed")
    elif req.decision == "edit":
        if not req.edited_text: raise HTTPException(status_code=400, detail="edited_text required")
        save_stage_output(doc_id=doc_id, stage=5, input_text=typeset_text, output_text=req.edited_text, operator="human",
                          human_notes=json.dumps({"reviewer": user["name"], "notes": req.notes}, ensure_ascii=False))
        log_audit(doc_id, "stage5_edited", {"reviewer": user["name"]}); update_document_stage(doc_id, 5, status="completed")
    elif req.decision == "reject":
        log_audit(doc_id, "stage5_rejected", {"reviewer": user["name"], "notes": req.notes})
    else: raise HTTPException(status_code=400, detail="Invalid decision")
    return _build_response(doc_id)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8081))
    uvicorn.run(app, host="0.0.0.0", port=port)
