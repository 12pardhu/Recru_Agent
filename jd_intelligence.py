import io, json, os, re, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
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
        CREATE TABLE IF NOT EXISTS job_versions(id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, version INTEGER NOT NULL, snapshot_json TEXT NOT NULL, changed_at TEXT NOT NULL, changed_by TEXT DEFAULT 'Recruiter', UNIQUE(job_id,version));
        """)
init()

SKILLS = ["Java","Spring Boot","Microservices","REST API","SQL","PostgreSQL","Python","JavaScript","TypeScript","React","Node.js","AWS","Azure","GCP","Machine Learning","Deep Learning","PyTorch","TensorFlow","LLM","Spark","Kafka","Docker","Kubernetes","Jenkins","CI/CD","Snowflake","Databricks","C#",".NET","Terraform","Salesforce","GenAI","LangChain","RAG","Power BI","Tableau","Oracle","MongoDB","Redis"]

def section(text, headings):
    names = "|".join(re.escape(x) for x in headings)
    stop = r"(?:preferred(?: skills)?|optional(?: skills)?|responsibilities|what you'll do|what you will do|job duties|qualifications|requirements|experience|locations?|location preference|work authorization|employment type|rate|compensation|education|certifications?|travel|relocation)"
    m = re.search(r"(?ims)^[ \t]*(?:" + names + r")[ \t]*:?[ \t]*(.*?)(?=^[ \t]*(?:" + stop + r")[ \t]*:?[ \t]*$|\Z)", text)
    return m.group(1).strip() if m else ""

def first_evidence(text, terms):
    if not terms: return ""
    for line in text.splitlines():
        if any(re.search(re.escape(str(t)), line, re.I) for t in terms):
            return line.strip()[:300]
    return ""

def analyze(text):
    lines = [x.strip(" •-*\t") for x in text.splitlines() if x.strip()]
    title = ""
    for line in lines[:15]:
        m = re.match(r"^(?:job title|position|role)\s*:\s*(.+)$", line, re.I)
        if m: title = m.group(1).strip(); break
        if len(line) < 100 and not re.match(r"^(experience|locations?|mandatory|preferred|required|responsibilities|qualifications|requirements|rate|work authorization)\s*:", line, re.I):
            title = line; break
    title = title or "New Job Requirement"
    low = text.lower()

    # Total and role-specific experience are kept separate; no ambiguous value is silently substituted.
    total = re.search(r"total\s+experience\s*(?:of|:)?\s*(\d+)\s*\+?\s*(?:years?|yrs?)", text, re.I)
    if not total:
        total = next((m for m in re.finditer(r"(\d+)\s*\+?\s*(?:years?|yrs?)", text, re.I)
                      if not re.match(r"\s*(?:of\s+)?(?:relevant|related|hands-on)", text[m.end():], re.I)), None)
    relevant = re.search(r"(\d+)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant|related|hands-on)\s+experience", text, re.I)
    tech_years = {}
    for skill in SKILLS:
        m = re.search(r"(\d+)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:experience\s+(?:in|with)\s+)?"+re.escape(skill)+r"\b", text, re.I)
        if not m:
            m = re.search(re.escape(skill)+r"\s*[:\-]?\s*(\d+)\s*\+?\s*(?:years?|yrs?)", text, re.I)
        if m: tech_years[skill] = int(m.group(1))

    loc_match = re.search(r"^\s*(?:locations?|location preference)\s*[:\-]\s*(.+?)\s*$", text, re.I | re.M)
    locations = []
    if loc_match:
        # Keep city/state pairs intact; semicolon, slash, pipe and explicit "and" delimit locations.
        locations = [x.strip(" ,") for x in re.split(r"\s*(?:;|\||/|\band\b|,\s*(?=[A-Z][A-Za-z .'-]+,\s*[A-Z]{2}\b))\s*", loc_match.group(1)) if x.strip(" ,")]
    else:
        m = re.search(r"\b(?:based in|location is)\s+([^\n.]+)", text, re.I)
        if m: locations = [m.group(1).strip()]

    mandatory_text = section(text, ["mandatory skills","mandatory","required skills","required qualifications","must have","must-have"])
    preferred_text = section(text, ["preferred skills","preferred","nice to have","nice-to-have","good to have"])
    optional_text = section(text, ["optional skills","optional"])
    def find_skills(source):
        return [s for s in SKILLS if re.search(r"(?<![\w])"+re.escape(s)+r"(?![\w])", source, re.I)]
    mandatory = find_skills(mandatory_text) if mandatory_text else []
    preferred = find_skills(preferred_text) if preferred_text else []
    optional = find_skills(optional_text) if optional_text else []
    if not mandatory_text and not preferred_text:
        mandatory = find_skills(text)
    mandatory = [s for s in mandatory if s.lower() not in {p.lower() for p in preferred + optional}]
    preferred = [s for s in preferred if s.lower() not in {o.lower() for o in optional}]

    auth_terms = ["STEM OPT","OPT","H-1B","Green Card","US Citizen","EAD"]
    auth = [x for x in auth_terms if re.search(re.escape(x), text, re.I)]
    employment_terms = ["C2C","W2","Contract-to-Hire","Full-time","1099","Contract"]
    employment = [x for x in employment_terms if re.search(r"\b"+re.escape(x)+r"\b",text,re.I)]
    rate = re.search(r"(?:rate|pay|compensation|salary)\s*[:\-]?\s*([^\n]+)", text, re.I)
    arrangements = [x for x in ["Remote","Hybrid","Onsite","On-site"] if re.search(r"\b"+re.escape(x)+r"\b",text,re.I)]
    domain = next((d for d, keys in [("AI/ML",["machine learning","deep learning","ai/ml","llm","genai"]),("Data Engineering",["data engineer","spark","kafka","databricks"]),("Cloud/DevOps",["devops engineer","cloud engineer","terraform"]),("QA/Testing",["qa engineer","quality assurance","automation testing"]),("Cybersecurity",["cybersecurity","security engineer"]),("Software Engineering",["software engineer","developer","java","python"])] if any(k in low for k in keys)), "General IT")
    responsibilities = section(text, ["responsibilities","what you'll do","what you will do","job duties"])
    education = section(text, ["education","education requirements"])
    certifications = section(text, ["certifications","certification requirements"])
    travel = re.search(r"[^\n]*(?:travel|travel requirement)[^\n]*", text, re.I)
    relocation = re.search(r"[^\n]*(?:relocation|relocate)[^\n]*", text, re.I)
    tech_versions = {}
    for skill in SKILLS:
        version = re.search(re.escape(skill)+r"\s*(?:version)?\s*(\d+(?:\.\d+)*)", text, re.I)
        if version: tech_versions[skill] = version.group(1)
    fields = {
      "title":title,"domain":domain,"locations":locations,
      "min_experience":int(total.group(1)) if total else None,
      "relevant_experience":int(relevant.group(1)) if relevant else None,
      "technology_experience":tech_years,
      "mandatory_skills":mandatory,"preferred_skills":preferred,"optional_skills":optional,"technology_versions":tech_versions,
      "work_authorization":auth,"employment_type":employment or ["Unknown"],
      "rate":rate.group(1).strip() if rate else "",
      "work_arrangement":arrangements,"responsibilities":responsibilities,"education":education,"certifications":certifications,"travel":travel.group(0).strip() if travel else "","relocation":relocation.group(0).strip() if relocation else ""
    }
    evidence = {}
    employment_conflict = {"C2C","W2"}.issubset(set(employment))
    for key, value in fields.items():
        terms = value if isinstance(value,list) else list(value.keys()) if isinstance(value,dict) else [value] if value not in ("",None) else []
        snippet = first_evidence(text, terms)
        missing = value in ("",[],None,{}) or value == ["Unknown"] or value == "New Job Requirement"
        status = "Conflicting" if key == "employment_type" and employment_conflict else ("Missing" if missing else "Needs review")
        evidence[key] = {"status":status,"evidence":snippet}
    return {"fields":fields,"evidence":evidence}

def quality_report(text, fields):
    warnings = []
    blockers = []
    title = str(fields.get("title","")).strip()
    if not title or title == "New Job Requirement":
        blockers.append({"field":"title","message":"A clear job title is required."})
    if not fields.get("mandatory_skills") and not fields.get("preferred_skills"):
        warnings.append({"field":"skills","message":"No skills were identified. Review the JD and add required skills if applicable."})
    if not fields.get("locations"):
        warnings.append({"field":"locations","message":"No work location was identified."})
    if fields.get("min_experience") is None:
        warnings.append({"field":"min_experience","message":"Total experience was not identified."})
    if fields.get("work_authorization") == []:
        warnings.append({"field":"work_authorization","message":"Work authorization is not stated. It will remain Unknown."})
    if fields.get("employment_type") in ([],["Unknown"]):
        warnings.append({"field":"employment_type","message":"Employment type is not stated. It will remain Unknown."})
    if len(fields.get("work_arrangement") or []) > 1:
        warnings.append({"field":"work_arrangement","message":"Multiple work arrangements appear in the JD. Confirm which are accepted."})
    if fields.get("relevant_experience") and fields.get("min_experience") and fields["relevant_experience"] > fields["min_experience"]:
        warnings.append({"field":"experience","message":"Relevant experience is greater than total experience. Verify both values."})
    if mandatory_conflict := ({x.lower() for x in fields.get("mandatory_skills",[])} & {x.lower() for x in fields.get("preferred_skills",[])}):
        warnings.append({"field":"skills","message":"Some skills are classified as both mandatory and preferred: "+", ".join(sorted(mandatory_conflict))})
    return {"ready_to_confirm":not blockers,"blockers":blockers,"warnings":warnings,"field_status":{k:v["status"] for k,v in analyze(text)["evidence"].items()}}

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

@router.get("/drafts/{draft_id}/document")
def download_original_document(draft_id: str):
    d = read_draft(draft_id)
    if not d.get("stored_path"):
        raise HTTPException(404,"This draft was created from pasted text; there is no uploaded original file.")
    path = Path(d["stored_path"]).resolve()
    if DOCS.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404,"The original uploaded file is not available in this environment.")
    return FileResponse(path, filename=d.get("original_filename") or path.name)

@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str):
    return read_draft(draft_id)

@router.patch("/drafts/{draft_id}")
def edit_draft(draft_id: str, payload: DraftEdit):
    d = read_draft(draft_id)
    if d["status"] == "Confirmed": raise HTTPException(409,"Confirmed requirements are immutable here. Create a new draft for changes.")
    analysis = d["analysis"]; analysis["fields"].update(payload.fields)
    for key in payload.fields:
        analysis.setdefault("evidence",{})[key] = {"status":"Recruiter edited","evidence":"Updated by recruiter during draft review"}
    for key in ("employment_type","work_arrangement","work_authorization","locations","mandatory_skills","preferred_skills"):
        value = analysis["fields"].get(key)
        if isinstance(value,str):
            analysis["fields"][key] = [x.strip() for x in re.split(r"[,;]",value) if x.strip()]
    with connect() as c:
        c.execute("UPDATE jd_drafts SET jd_text=?,extracted_json=?,updated_at=? WHERE id=?",(payload.jd_text if payload.jd_text is not None else d["jd_text"],json.dumps(analysis),stamp(),draft_id))
    return read_draft(draft_id)

@router.get("/drafts/{draft_id}/quality")
def draft_quality(draft_id: str):
    d = read_draft(draft_id)
    return quality_report(d["jd_text"],d["analysis"]["fields"])

@router.post("/drafts/{draft_id}/confirm")
def confirm_draft(draft_id: str, payload: dict = None):
    d = read_draft(draft_id)
    if d["status"] == "Confirmed": return {"job_id":d["confirmed_job_id"],"message":"Already confirmed."}
    f = d["analysis"]["fields"]; report = quality_report(d["jd_text"],f)
    if not report["ready_to_confirm"]:
        raise HTTPException(400,{"message":"Resolve the blocking fields before confirming.","quality":report})
    if report["warnings"] and not (payload or {}).get("acknowledge_warnings"):
        raise HTTPException(409,{"message":"Review the quality warnings and explicitly acknowledge them before confirming.","quality":report})
    title = str(f.get("title","")).strip()
    locations = f.get("locations") or []; location = "; ".join(locations) if isinstance(locations,list) else str(locations)
    skills = ", ".join(f.get("mandatory_skills") or []); preferred = ", ".join(f.get("preferred_skills") or [])
    auth = ", ".join(f.get("work_authorization") or []) or "Unknown"
    for key in d["analysis"].get("evidence",{}):
        value = f.get(key)
        missing = value in ("", [], None, {}) or value == ["Unknown"] or value == "New Job Requirement"
        d["analysis"]["evidence"][key]["status"] = "Missing" if missing else "Recruiter confirmed"
    employment_value = f.get("employment_type") or ["Unknown"]
    employment = ", ".join(employment_value if isinstance(employment_value,list) else [str(employment_value)])
    with connect() as c:
        c.execute("UPDATE jd_drafts SET extracted_json=? WHERE id=?",(json.dumps(d["analysis"]),draft_id))
        existing_job_id = d.get("confirmed_job_id")
        if existing_job_id:
            current = c.execute("SELECT id FROM jobs WHERE id=?",(existing_job_id,)).fetchone()
            if not current: raise HTTPException(404,"The requirement being revised no longer exists.")
            c.execute("UPDATE jobs SET title=?,location=?,min_experience=?,skills=?,work_auth=?,jd_text=?,domain=?,preferred_skills=?,employment_type=? WHERE id=?",
              (title,location,int(f.get("min_experience") or 0),skills,auth,d["jd_text"],f.get("domain",""),preferred,employment,existing_job_id))
            jid = existing_job_id
            version = c.execute("SELECT COALESCE(MAX(version),0)+1 AS next_version FROM job_versions WHERE job_id=?",(jid,)).fetchone()["next_version"]
        else:
            cur = c.execute("INSERT INTO jobs(title,location,min_experience,skills,work_auth,jd_text,created_at,domain,preferred_skills,employment_type,source_mode) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(title,location,int(f.get("min_experience") or 0),skills,auth,d["jd_text"],stamp(),f.get("domain",""),preferred,employment,"both"))
            jid = cur.lastrowid
            version = 1
        c.execute("INSERT INTO job_versions(job_id,version,snapshot_json,changed_at) VALUES(?,?,?,?)",(jid,version,json.dumps({"fields":f,"quality":report}),stamp()))
        c.execute("UPDATE jd_drafts SET status='Confirmed',updated_at=? WHERE id=?",(stamp(),draft_id))
    return {"job_id":jid,"message":"Requirement confirmed and saved. Sourcing has not started; use Candidate Sourcing when ready.","quality":report}

@router.post("/jobs/{job_id}/revision")
def create_revision_draft(job_id: int):
    with connect() as c:
        job = c.execute("SELECT * FROM jobs WHERE id=?",(job_id,)).fetchone()
    if not job: raise HTTPException(404,"Job not found")
    job = dict(job)
    fields = {
      "title":job["title"],"domain":job.get("domain",""),
      "locations":[x.strip() for x in (job.get("location") or "").split(";") if x.strip()],
      "min_experience":job.get("min_experience"),"relevant_experience":None,"technology_experience":{},
      "mandatory_skills":[x.strip() for x in (job.get("skills") or "").split(",") if x.strip()],
      "preferred_skills":[x.strip() for x in (job.get("preferred_skills") or "").split(",") if x.strip()],"optional_skills":[],"technology_versions":{},
      "work_authorization":[x.strip() for x in (job.get("work_auth") or "").split(",") if x.strip() and x.strip()!="Unknown"],
      "employment_type":[x.strip() for x in (job.get("employment_type") or "Unknown").split(",") if x.strip()],
      "rate":"","work_arrangement":[],"responsibilities":"","education":"","certifications":"","travel":"","relocation":""
    }
    result = {"fields":fields,"evidence":{k:{"status":"Needs review","evidence":"Copied from the previously confirmed requirement"} for k in fields}}
    did = str(uuid.uuid4())
    with connect() as c:
        c.execute("INSERT INTO jd_drafts(id,original_filename,stored_path,jd_text,extracted_json,status,created_at,updated_at,confirmed_job_id) VALUES(?,?,?,?,?,'Needs review',?,?,?)",
          (did,"Revision of Job #"+str(job_id),"",job.get("jd_text",""),json.dumps(result),stamp(),stamp(),job_id))
    return read_draft(did)

@router.get("/jobs/{job_id}/versions")
def get_versions(job_id: int):
    with connect() as c: rows = c.execute("SELECT version,snapshot_json,changed_at,changed_by FROM job_versions WHERE job_id=? ORDER BY version DESC",(job_id,)).fetchall()
    return [{"version":r["version"],"fields":json.loads(r["snapshot_json"]),"changed_at":r["changed_at"],"changed_by":r["changed_by"]} for r in rows]
