import io, json, os, re, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

ROOT = Path(__file__).parent
DATA = Path(os.getenv("DATA_DIR", str(ROOT / "data")))
DATA.mkdir(parents=True, exist_ok=True)
DOCS = DATA / "job_documents"
DOCS.mkdir(parents=True, exist_ok=True)
DB = DATA / "recru_agent.db"
router = APIRouter(prefix="/api/jd", tags=["Job Requirement Intelligence"])

def connect():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def stamp():
    return datetime.now(timezone.utc).isoformat()

def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS jd_drafts(id TEXT PRIMARY KEY, original_filename TEXT DEFAULT '', stored_path TEXT DEFAULT '', jd_text TEXT NOT NULL, extracted_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Needs review', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, confirmed_job_id INTEGER);
        CREATE TABLE IF NOT EXISTS job_versions(id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, version INTEGER NOT NULL, snapshot_json TEXT NOT NULL, changed_at TEXT NOT NULL, changed_by TEXT DEFAULT 'Recruiter');
        """)
init()

def analyze(text):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    title = next((re.sub(r"^(?:job title|position|role)\s*:\s*", "", x, flags=re.I) for x in lines[:12] if len(x) < 100 and not re.match(r"^(experience|locations?|mandatory|preferred|responsibilities)\s*:", x, re.I)), "New Job Requirement")
    low = text.lower()
    exp = re.search(r"(\d+)\s*\+?\s*(?:years?|yrs?)", low)
    loc_match = re.search(r"^\s*locations?\s*[:\-]\s*(.+?)\s*$", text, re.I | re.M)
    locations = [x.strip(" ,") for x in re.split(r"\s*(?:;|\||\s+and\s+)\s*", loc_match.group(1)) if x.strip(" ,")] if loc_match else []
    skills_bank = ["Java","Spring Boot","Microservices","REST API","SQL","PostgreSQL","Python","JavaScript","TypeScript","React","Node.js","AWS","Azure","GCP","Machine Learning","Deep Learning","PyTorch","TensorFlow","LLM","Spark","Kafka","Docker","Kubernetes","Jenkins","CI/CD","Snowflake","Databricks","C#",".NET"]
    def skills_in(source):
        return [s for s in skills_bank if re.search(r"(?<![\w])"+re.escape(s)+r"(?![\w])", source, re.I)]
    def section(name):
        m = re.search(r"(?ims)^"+name+r"\s*:?\s*$\n(.*?)(?=^(?:mandatory|preferred|optional|responsibilities|qualifications|requirements|location|experience)\s*:?\s*$|\Z)", text)
        return m.group(1) if m else ""
    mandatory = skills_in(section("mandatory")) if section("mandatory") else []
    preferred = skills_in(section("preferred")) if section("preferred") else []
    if not mandatory and not section("mandatory"):
        mandatory = [s for s in skills_in(text) if s not in preferred]
    auth = [x for x in ["STEM OPT","OPT","H-1B","Green Card","US Citizen"] if re.search(re.escape(x), text, re.I)]
    employment = next((x for x in ["C2C","W2","Contract-to-Hire","Full-time","1099","Contract"] if re.search(r"\b"+re.escape(x)+r"\b",text,re.I)), "Unknown")
    rate = re.search(r"(?:rate|pay|compensation)\s*[:\-]?\s*([^\n]+)", text, re.I)
    domain = next((d for d, keys in [("AI/ML",["machine learning","deep learning","ai/ml","llm"]),("Data Engineering",["data engineer","spark","kafka","databricks"]),("Cloud/DevOps",["devops engineer","cloud engineer","terraform"]),("Software Engineering",["developer","software engineer","java","python"])] if any(k in low for k in keys)), "General IT")
    fields = {"title":title,"domain":domain,"locations":locations,"min_experience":int(exp.group(1)) if exp else None,"mandatory_skills":mandatory,"preferred_skills":preferred,"work_authorization":auth,"employment_type":employment,"rate":rate.group(1).strip() if rate else "","work_arrangement":next((x for x in ["Remote","Hybrid","Onsite"] if re.search(r"\b"+x+r"\b",text,re.I)),"")}
    evidence = {k:{"status":"Missing" if v in ("",[],None) else "Needs review","evidence":str(v) if v not in ("",[],None) else ""} for k,v in fields.items()}
    return {"fields":fields,"evidence":evidence}

def read_draft(draft_id):
    with connect() as c: row = c.execute("SELECT * FROM jd_drafts WHERE id=?", (draft_id,)).fetchone()
    if not row: raise HTTPException(404,"JD draft not found")
    out = dict(row); out["analysis"] = json.loads(out.pop("extracted_json")); return out

def save_draft(text, filename="", path=""):
    if not text.strip(): raise HTTPException(400,"No readable JD text found.")
    did = str(uuid.uuid4()); result = analyze(text)
    with connect() as c:
        c.execute("INSERT INTO jd_drafts(id,original_filename,stored_path,jd_text,extracted_json,status,created_at,updated_at) VALUES(?,?,?,?,?,'Needs review',?,?)",(did,filename,path,text,json.dumps(result),stamp(),stamp()))
    return read_draft(did)

class DraftEdit(BaseModel):
    fields: dict
    jd_text: str | None = None

@router.post("/drafts")
def create_pasted_draft(payload: dict):
    return save_draft(str(payload.get("jd_text","")))

@router.post("/drafts/upload")
async def upload_draft(file: UploadFile = File(...)):
    filename = file.filename or "job-description"
    raw = await file.read(); ext = Path(filename).suffix.lower()
    try:
        if ext in (".txt",".md"): text = raw.decode("utf-8-sig",errors="replace")
        elif ext == ".pdf":
            from pypdf import PdfReader
            text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(raw)).pages)
        elif ext == ".docx":
            from docx import Document
            text = "\n".join(p.text for p in Document(io.BytesIO(raw)).paragraphs)
        else: raise HTTPException(415,"Supported formats: TXT, MD, PDF, DOCX.")
    except HTTPException: raise
    except Exception as e: raise HTTPException(400,"Could not read this document. Scanned PDFs need OCR.") from e
    if not text.strip(): raise HTTPException(400,"No readable text found. Scanned PDFs need OCR.")
    path = DOCS / (uuid.uuid4().hex + ext); path.write_bytes(raw)
    return save_draft(text,filename,str(path))

@router.get("/drafts")
def list_drafts():
    with connect() as conn:
        rows = conn.execute("SELECT id,original_filename,status,created_at,updated_at FROM jd_drafts ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str):
    return read_draft(draft_id)

@router.patch("/drafts/{draft_id}")
def edit_draft(draft_id: str, payload: DraftEdit):
    d = read_draft(draft_id); analysis = d["analysis"]; analysis["fields"].update(payload.fields)
    with connect() as c:
        c.execute("UPDATE jd_drafts SET jd_text=?,extracted_json=?,updated_at=? WHERE id=?",(payload.jd_text if payload.jd_text is not None else d["jd_text"],json.dumps(analysis),stamp(),draft_id))
    return read_draft(draft_id)

@router.post("/drafts/{draft_id}/confirm")
def confirm_draft(draft_id: str):
    d = read_draft(draft_id)
    if d["status"] == "Confirmed": return {"job_id":d["confirmed_job_id"],"message":"Already confirmed."}
    f = d["analysis"]["fields"]; title = str(f.get("title","")).strip()
    if not title or title == "New Job Requirement": raise HTTPException(400,"Review and enter a job title before confirming.")
    locations = f.get("locations") or []; location = "; ".join(locations) if isinstance(locations,list) else str(locations)
    skills = ", ".join(f.get("mandatory_skills") or []); preferred = ", ".join(f.get("preferred_skills") or [])
    auth = ", ".join(f.get("work_authorization") or []) or "Unknown"
    with connect() as c:
        cur = c.execute("INSERT INTO jobs(title,location,min_experience,skills,work_auth,jd_text,created_at,domain,preferred_skills,employment_type,source_mode) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(title,location,int(f.get("min_experience") or 0),skills,auth,d["jd_text"],stamp(),f.get("domain",""),preferred,f.get("employment_type","Unknown"),"both"))
        jid = cur.lastrowid
        c.execute("INSERT INTO job_versions(job_id,version,snapshot_json,changed_at) VALUES(?,1,?,?)",(jid,json.dumps(f),stamp()))
        c.execute("UPDATE jd_drafts SET status='Confirmed',confirmed_job_id=?,updated_at=? WHERE id=?",(jid,stamp(),draft_id))
    return {"job_id":jid,"message":"Requirement confirmed and saved. Sourcing has not started; use Candidate Sourcing when ready."}

@router.get("/jobs/{job_id}/versions")
def get_versions(job_id: int):
    with connect() as c: rows = c.execute("SELECT version,snapshot_json,changed_at,changed_by FROM job_versions WHERE job_id=? ORDER BY version DESC",(job_id,)).fetchall()
    return [{"version":r["version"],"fields":json.loads(r["snapshot_json"]),"changed_at":r["changed_at"],"changed_by":r["changed_by"]} for r in rows]
