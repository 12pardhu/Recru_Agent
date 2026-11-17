from pathlib import Path
import os, sqlite3, re
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR", str(ROOT/"data")))
DATA.mkdir(parents=True, exist_ok=True)
DB=DATA/"recru_agent.db"
app=FastAPI(title="Recru Agent - AI OPT Recruiter Agent", version="2.0.0")

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, title TEXT NOT NULL, location TEXT DEFAULT '', min_experience INTEGER DEFAULT 0, skills TEXT DEFAULT '', work_auth TEXT DEFAULT 'Unknown', jd_text TEXT DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS candidates(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT DEFAULT '', location TEXT DEFAULT '', experience REAL DEFAULT 0, skills TEXT DEFAULT '', work_auth TEXT DEFAULT 'Unknown', c2c_status TEXT DEFAULT 'Unknown', linkedin_url TEXT DEFAULT '', resume_text TEXT DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS approvals(id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL, job_id INTEGER NOT NULL, status TEXT DEFAULT 'Pending', notes TEXT DEFAULT '', created_at TEXT NOT NULL);
        """)
init()
def now(): return datetime.now(timezone.utc).isoformat()
def rows(q,args=()):
    with connect() as c: return [dict(x) for x in c.execute(q,args).fetchall()]
class JobIn(BaseModel):
    title:str
    location:str=""
    min_experience:int=0
    skills:str=""
    work_auth:str="Unknown"
    jd_text:str=""
class CandidateIn(BaseModel):
    name:str
    email:str=""
    location:str=""
    experience:float=0
    skills:str=""
    work_auth:str="Unknown"
    c2c_status:str="Unknown"
    linkedin_url:str=""
    resume_text:str=""
@app.get("/api/health")
def health(): return {"status":"ok","app":"Recru Agent","version":"2.0.0"}
@app.get("/api/dashboard")
def dashboard():
    return {"jobs":len(rows("SELECT id FROM jobs")),"candidates":len(rows("SELECT id FROM candidates")),"pending_approvals":len(rows("SELECT id FROM approvals WHERE status='Pending'"))}
@app.get("/api/jobs")
def get_jobs(): return rows("SELECT * FROM jobs ORDER BY id DESC")
@app.post("/api/jobs")
def add_job(j:JobIn):
    if not j.title.strip(): raise HTTPException(400,"Job title is required")
    with connect() as c:
        cur=c.execute("INSERT INTO jobs(title,location,min_experience,skills,work_auth,jd_text,created_at) VALUES(?,?,?,?,?,?,?)",(j.title,j.location,j.min_experience,j.skills,j.work_auth,j.jd_text,now()))
        return {"id":cur.lastrowid,"message":"Job requirement saved"}
@app.get("/api/candidates")
def get_candidates(): return rows("SELECT * FROM candidates ORDER BY id DESC")
@app.post("/api/candidates")
def add_candidate(p:CandidateIn):
    if not p.name.strip(): raise HTTPException(400,"Candidate name is required")
    with connect() as c:
        cur=c.execute("INSERT INTO candidates(name,email,location,experience,skills,work_auth,c2c_status,linkedin_url,resume_text,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(p.name,p.email,p.location,p.experience,p.skills,p.work_auth,p.c2c_status,p.linkedin_url,p.resume_text,now()))
        return {"id":cur.lastrowid,"message":"Candidate saved"}
@app.post("/api/jobs/{job_id}/match")
def match(job_id:int):
    jobs=rows("SELECT * FROM jobs WHERE id=?",(job_id,))
    if not jobs: raise HTTPException(404,"Job not found")
    j=jobs[0]; required={x.strip().lower() for x in j["skills"].split(",") if x.strip()}
    out=[]
    for p in rows("SELECT * FROM candidates"):
        skills={x.strip().lower() for x in p["skills"].split(",") if x.strip()}
        overlap=required & skills
        score=round(100*(len(overlap)/len(required)) if required else 0)
        if j["min_experience"] and p["experience"]>=j["min_experience"]: score=min(100,score+15)
        if j["location"] and j["location"].lower() in p["location"].lower(): score=min(100,score+10)
        out.append({"candidate":p,"score":score,"matched_skills":sorted(overlap),"missing_skills":sorted(required-skills),"work_auth":p["work_auth"],"c2c_status":p["c2c_status"]})
    return sorted(out,key=lambda x:x["score"],reverse=True)
@app.post("/api/jobs/upload")
async def upload_jd(file:UploadFile=File(...)):
    name=file.filename or ""
    if not name.lower().endswith((".txt",".md")): raise HTTPException(415,"For this starter version, upload a .txt or .md job description.")
    text=(await file.read()).decode("utf-8",errors="replace")
    title=next((line.strip("# -*\t ") for line in text.splitlines() if line.strip()),"New Job Requirement")
    return {"title":title[:120],"jd_text":text}
@app.post("/api/approvals")
def create_approval(payload:dict):
    with connect() as c:
        cur=c.execute("INSERT INTO approvals(candidate_id,job_id,status,notes,created_at) VALUES(?,?, 'Pending',?,?)",(int(payload["candidate_id"]),int(payload["job_id"]),str(payload.get("notes","")),now()))
        return {"id":cur.lastrowid,"status":"Pending"}
@app.get("/api/approvals")
def get_approvals(): return rows("SELECT a.*,p.name candidate_name,j.title job_title FROM approvals a JOIN candidates p ON p.id=a.candidate_id JOIN jobs j ON j.id=a.job_id ORDER BY a.id DESC")
@app.patch("/api/approvals/{approval_id}")
def update_approval(approval_id:int,payload:dict):
    status=payload.get("status")
    if status not in ("Approved","Rejected"): raise HTTPException(400,"Status must be Approved or Rejected")
    with connect() as c:
        cur=c.execute("UPDATE approvals SET status=?,notes=? WHERE id=?",(status,str(payload.get("notes","")),approval_id))
        if not cur.rowcount: raise HTTPException(404,"Approval not found")
    return {"id":approval_id,"status":status}
app.mount("/static",StaticFiles(directory=ROOT/"static"),name="static")
@app.get("/",response_class=HTMLResponse)
def home(): return (ROOT/"static"/"index.html").read_text(encoding="utf-8")
