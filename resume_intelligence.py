import io, json, os, re, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT = Path(__file__).parent
DATA = Path(os.getenv("DATA_DIR", str(ROOT / "data")))
DATA.mkdir(parents=True, exist_ok=True)
DOCS = DATA / "resume_documents"
DOCS.mkdir(parents=True, exist_ok=True)
DB = DATA / "recru_agent.db"
router = APIRouter(prefix="/api/resumes", tags=["Resume Intelligence"])

def connect():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def stamp():
    return datetime.now(timezone.utc).isoformat()

def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS resume_drafts(
          id TEXT PRIMARY KEY, original_filename TEXT DEFAULT '', stored_path TEXT DEFAULT '',
          resume_text TEXT NOT NULL, parsed_json TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'Needs review', created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL, candidate_id INTEGER
        );
        """)
init()

SKILLS = ["Java","Spring Boot","Microservices","REST API","SQL","PostgreSQL","Python","JavaScript","TypeScript","React","Node.js","AWS","Azure","GCP","Machine Learning","Deep Learning","PyTorch","TensorFlow","LLM","Spark","Kafka","Docker","Kubernetes","Jenkins","CI/CD","Snowflake","Databricks","C#",".NET","Terraform","Salesforce","GenAI","LangChain","RAG","Power BI","Tableau","Oracle","MongoDB","Redis","HTML","CSS","Git"]

def extract_section(text, headings, stops):
    h = "|".join(re.escape(x) for x in headings)
    s = "|".join(re.escape(x) for x in stops)
    m = re.search(r"(?ims)^[ \t]*(?:" + h + r")[ \t]*:?[ \t]*(.*?)(?=^[ \t]*(?:" + s + r")[ \t]*:?[ \t]*$|\Z)", text)
    return m.group(1).strip() if m else ""

def parse_resume(text):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    name = ""
    for line in lines[:8]:
        if len(line) <= 80 and not re.search(r"@|https?://|linkedin\.com|github\.com|\+?\d[\d ()-]{7,}", line, re.I) and line.lower() not in ("resume","curriculum vitae","cv","profile"):
            name = line; break
    email_m = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
    phone_m = re.search(r"(?<!\w)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\w)", text)
    location_m = re.search(r"^\s*(?:location|based in|address)\s*[:\-]\s*([^\n]+)", text, re.I | re.M)
    exp_matches = list(re.finditer(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+)?experience", text, re.I))
    experience = float(exp_matches[0].group(1)) if exp_matches else None
    skills = [s for s in SKILLS if re.search(r"(?<![\w])"+re.escape(s)+r"(?![\w])", text, re.I)]
    stops = ["education","certifications","skills","technical skills","professional experience","work experience","projects"]
    education = extract_section(text, ["education","academic background"], ["certifications","skills","technical skills","professional experience","work experience","projects"])
    certifications = extract_section(text, ["certifications","certificates"], ["education","skills","technical skills","professional experience","work experience","projects"])
    work = extract_section(text, ["professional experience","work experience","employment history","experience"], ["education","certifications","skills","technical skills","projects"])
    projects = extract_section(text, ["projects","personal projects"], ["education","certifications","skills","technical skills","professional experience","work experience"])
    summary = extract_section(text, ["professional summary","summary","profile"], ["skills","technical skills","professional experience","work experience","education"])
    links = list(dict.fromkeys(re.findall(r"https?://(?:www\.)?(?:linkedin\.com|github\.com)/[^\s)>]+", text, re.I)))
    fields = {"name":name,"email":email_m.group(0) if email_m else "",
      "phone":phone_m.group(0).strip() if phone_m else "",
      "location":location_m.group(1).strip() if location_m else "",
      "experience":experience,"skills":skills,"education":education,
      "certifications":certifications,"work_history":work,"projects":projects,
      "summary":summary,"profile_links":links}
    evidence = {}
    for key,value in fields.items():
        missing = value in ("",[],None)
        evidence[key] = {"status":"Missing" if missing else "Needs review","evidence":str(value)[:300] if not missing else ""}
    return {"fields":fields,"evidence":evidence}

def read_draft(draft_id):
    with connect() as c:
        row = c.execute("SELECT * FROM resume_drafts WHERE id=?",(draft_id,)).fetchone()
    if not row: raise HTTPException(404,"Resume draft not found.")
    out = dict(row); out["analysis"] = json.loads(out.pop("parsed_json")); return out

def save_draft(text,filename="",path=""):
    if not text.strip(): raise HTTPException(400,"No readable resume text found.")
    draft_id=str(uuid.uuid4()); parsed=parse_resume(text)
    with connect() as c:
        c.execute("INSERT INTO resume_drafts(id,original_filename,stored_path,resume_text,parsed_json,status,created_at,updated_at) VALUES(?,?,?,?,?,'Needs review',?,?)",
          (draft_id,filename,path,text,json.dumps(parsed),stamp(),stamp()))
    return read_draft(draft_id)

class ResumeEdit(BaseModel):
    fields: dict
    resume_text: str | None = None

@router.post("/drafts")
def create_pasted_resume(payload: dict):
    return save_draft(str(payload.get("resume_text","")))

@router.post("/drafts/upload")
async def upload_resume(file: UploadFile = File(...)):
    filename=file.filename or "resume"
    raw=await file.read(); ext=Path(filename).suffix.lower()
    if len(raw)>15*1024*1024: raise HTTPException(413,"Resume files must be 15 MB or smaller.")
    try:
        if ext in (".txt",".md"): text=raw.decode("utf-8-sig",errors="replace")
        elif ext==".pdf":
            from pypdf import PdfReader
            text="\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(raw)).pages)
        elif ext==".docx":
            from docx import Document
            doc=Document(io.BytesIO(raw)); parts=[p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows: parts.append(" | ".join(cell.text.strip() for cell in row.cells if cell.text.strip()))
            text="\n".join(parts)
        else: raise HTTPException(415,"Supported resume formats: PDF, DOCX, TXT, MD.")
    except HTTPException: raise
    except Exception as e: raise HTTPException(400,"Could not read this resume. Scanned PDFs need OCR.") from e
    if not text.strip(): raise HTTPException(400,"No readable resume text found. Scanned PDFs need OCR.")
    path=DOCS/(uuid.uuid4().hex+ext); path.write_bytes(raw)
    return save_draft(text,filename,str(path))

@router.get("/drafts")
def list_resume_drafts():
    with connect() as c:
        rows=c.execute("SELECT id,original_filename,status,created_at,updated_at,candidate_id FROM resume_drafts ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

@router.get("/drafts/{draft_id}")
def get_resume_draft(draft_id:str):
    return read_draft(draft_id)

@router.patch("/drafts/{draft_id}")
def edit_resume_draft(draft_id:str,payload:ResumeEdit):
    d=read_draft(draft_id)
    if d["status"]=="Attached": raise HTTPException(409,"This resume is already attached to a candidate. Upload a new revision to change it.")
    parsed=d["analysis"]; parsed["fields"].update(payload.fields)
    for key in payload.fields:
        parsed.setdefault("evidence",{})[key]={"status":"Recruiter edited","evidence":"Updated by recruiter during resume review"}
    with connect() as c:
        c.execute("UPDATE resume_drafts SET resume_text=?,parsed_json=?,updated_at=? WHERE id=?",
          (payload.resume_text if payload.resume_text is not None else d["resume_text"],json.dumps(parsed),stamp(),draft_id))
    return read_draft(draft_id)

@router.get("/drafts/{draft_id}/document")
def download_resume_document(draft_id:str):
    d=read_draft(draft_id)
    if not d.get("stored_path"): raise HTTPException(404,"This resume was pasted; there is no uploaded original file.")
    path=Path(d["stored_path"]).resolve()
    if DOCS.resolve() not in path.parents or not path.is_file(): raise HTTPException(404,"The uploaded original resume is not available.")
    return FileResponse(path,filename=d.get("original_filename") or path.name)
