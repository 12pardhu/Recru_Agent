from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote_plus
import csv, io, os, re, sqlite3
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR", str(ROOT/"data")))
DATA.mkdir(parents=True, exist_ok=True)
DB=DATA/"recru_agent.db"
app=FastAPI(title="Recru Agent", version="3.0.0")

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def now(): return datetime.now(timezone.utc).isoformat()
def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, title TEXT NOT NULL, location TEXT DEFAULT '', min_experience INTEGER DEFAULT 0, skills TEXT DEFAULT '', work_auth TEXT DEFAULT 'Unknown', jd_text TEXT DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS candidates(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT DEFAULT '', location TEXT DEFAULT '', experience REAL DEFAULT 0, skills TEXT DEFAULT '', work_auth TEXT DEFAULT 'Unknown', c2c_status TEXT DEFAULT 'Unknown', linkedin_url TEXT DEFAULT '', resume_text TEXT DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS approvals(id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL, job_id INTEGER NOT NULL, status TEXT DEFAULT 'Pending', notes TEXT DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sourcing_tasks(id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, mode TEXT NOT NULL, query_text TEXT NOT NULL, linkedin_url TEXT NOT NULL, status TEXT DEFAULT 'Prepared', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sourcing_searches(id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, location TEXT DEFAULT '', search_type TEXT DEFAULT 'Role + skills', query_text TEXT NOT NULL, linkedin_url TEXT NOT NULL, status TEXT DEFAULT 'Prepared', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sourcing_events(id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, event_type TEXT NOT NULL, details TEXT DEFAULT '', created_at TEXT NOT NULL);
        """)
        migrations={
          "jobs":{"domain":"TEXT DEFAULT ''","preferred_skills":"TEXT DEFAULT ''","employment_type":"TEXT DEFAULT 'Unknown'","source_mode":"TEXT DEFAULT 'both'"},
          "candidates":{"open_to_work":"TEXT DEFAULT 'Unknown'","availability_signal":"TEXT DEFAULT 'Unknown'","profile_updated":"TEXT DEFAULT ''","source_type":"TEXT DEFAULT 'Manual'","source_url":"TEXT DEFAULT ''","source_evidence":"TEXT DEFAULT ''","c2c_confirmed":"TEXT DEFAULT 'Unknown'","work_auth_confirmed":"TEXT DEFAULT 'Unknown'","sourcing_task_id":"INTEGER","phone":"TEXT DEFAULT ''","education":"TEXT DEFAULT ''","certifications":"TEXT DEFAULT ''","work_history":"TEXT DEFAULT ''","resume_draft_id":"TEXT DEFAULT ''","employment_preference":"TEXT DEFAULT 'Unknown'","employment_preference_confirmed":"TEXT DEFAULT 'Unknown'","contact_preference":"TEXT DEFAULT 'Unknown'","do_not_contact":"INTEGER DEFAULT 0"}
        }
        migrations["sourcing_tasks"]={"target_count":"INTEGER DEFAULT 50","notes":"TEXT DEFAULT ''","started_at":"TEXT DEFAULT ''","completed_at":"TEXT DEFAULT ''"}
        migrations["sourcing_searches"]={"search_type":"TEXT DEFAULT 'Role + skills'"}
        for table,cols in migrations.items():
            existing={r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
            for name,definition in cols.items():
                if name not in existing: c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
init()

def rows(sql,args=()):
    with db() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]
def tokens(s): return [x.strip() for x in re.split(r"[,;\n|]",s or "") if x.strip()]
def extract_jd(text):
    lines=[x.strip(" •-*\t") for x in text.splitlines() if x.strip()]
    title=next((x for x in lines if len(x)<100), "New Job Requirement")
    low=text.lower()
    skill_bank=["python","java","javascript","typescript","react","node.js","spring boot","microservices","aws","azure","gcp","sql","postgresql","machine learning","deep learning","pytorch","tensorflow","llm","data engineering","spark","kafka","salesforce"," .net","c#"," kubernetes","docker","terraform","snowflake","databricks"]
    found=[s.strip() for s in skill_bank if s.strip() and s.strip() in low]
    exp=re.search(r"(\d+)\s*\+?\s*(?:years|yrs)",low)
    loc=[]
    # Preserve every city/state pair from a labelled location line.
    m=re.search(r"^\s*locations?\s*[:\-]\s*(.+?)\s*$",text,re.I|re.M)
    if m:
        raw_location=m.group(1).strip()
        normalized=re.sub(r"\s*(?:/|\||;|\band\b)\s*","; ",raw_location,flags=re.I)
        loc=[x.strip(" ,") for x in normalized.split(";") if x.strip(" ,")]
    else:
        m=re.search(r"based in\s+([^\n]+)",text,re.I)
        if m: loc=[m.group(1).strip()]
    auth=next((x for x in ["STEM OPT","OPT","H-1B","Green Card","US Citizen"] if x.lower() in low),"Unknown")
    # Cloud keywords alone (for example AWS) must not override a software developer role.
    domain=next((x for x in ["AI/ML","Data Engineering","Software Engineering","Cloud/DevOps","QA/Testing","Cybersecurity"] if any(k in low for k in {"AI/ML":["machine learning","deep learning","llm","ai/ml"],"Data Engineering":["data engineer","spark","kafka","databricks"],"Software Engineering":["developer","software engineer","java","python"],"Cloud/DevOps":["devops engineer","cloud engineer","kubernetes","terraform"],"QA/Testing":["qa","automation testing"],"Cybersecurity":["security engineer","cybersecurity"]}[x])), "General IT")
    return {"title":title[:120],"domain":domain,"location":loc[0] if loc else "","min_experience":int(exp.group(1)) if exp else 0,"skills":", ".join(found),"preferred_skills":"","work_auth":auth,"employment_type":"Unknown","jd_text":text}

class JobIn(BaseModel):
    title:str
    location:str=""
    min_experience:int=0
    skills:str=""
    preferred_skills:str=""
    domain:str=""
    work_auth:str="Unknown"
    employment_type:str="Unknown"
    jd_text:str=""
    source_mode:str="both"
class CandidateIn(BaseModel):
    name:str
    email:str=""
    location:str=""
    experience:float=0
    skills:str=""
    work_auth:str="Unknown"
    c2c_status:str="Unknown"
    c2c_confirmed:str="Unknown"
    work_auth_confirmed:str="Unknown"
    linkedin_url:str=""
    resume_text:str=""
    open_to_work:str="Unknown"
    availability_signal:str="Unknown"
    profile_updated:str=""
    source_type:str="Manual"
    source_url:str=""
    source_evidence:str=""
    sourcing_task_id:int|None=None
    phone:str=""
    education:str=""
    certifications:str=""
    work_history:str=""
    resume_draft_id:str=""
    employment_preference:str="Unknown"
    employment_preference_confirmed:str="Unknown"
    contact_preference:str="Unknown"
    do_not_contact:bool=False

@app.get("/api/health")
def health(): return {"status":"ok","app":"Recru Agent","version":"3.0.0"}
@app.get("/api/dashboard")
def dashboard():
    return {"jobs":len(rows("SELECT id FROM jobs")),"candidates":len(rows("SELECT id FROM candidates")),"pending_approvals":len(rows("SELECT id FROM approvals WHERE status='Pending'")),"sourcing_tasks":len(rows("SELECT id FROM sourcing_tasks"))}
@app.get("/api/jobs")
def get_jobs(): return rows("SELECT * FROM jobs ORDER BY id DESC")
@app.post("/api/jobs")
def add_job(j:JobIn):
    if not j.title.strip(): raise HTTPException(400,"Job title is required")
    with db() as c:
        cur=c.execute("INSERT INTO jobs(title,location,min_experience,skills,work_auth,jd_text,created_at,domain,preferred_skills,employment_type,source_mode) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(j.title.strip(),j.location,j.min_experience,j.skills,j.work_auth,j.jd_text,now(),j.domain,j.preferred_skills,j.employment_type,j.source_mode))
        jid=cur.lastrowid
    return {"id":jid,"message":"Requirement saved without sourcing. Use Job Requirement Intelligence to review and confirm before sourcing."}
@app.get("/api/candidates")
def get_candidates(): return rows("SELECT * FROM candidates ORDER BY id DESC")
@app.post("/api/candidates")
def add_candidate(p:CandidateIn):
    with db() as c:
        resume_fields={}
        resume_text=p.resume_text
        if p.resume_draft_id:
            draft=c.execute("SELECT * FROM resume_drafts WHERE id=?",(p.resume_draft_id,)).fetchone()
            if not draft: raise HTTPException(404,"Resume draft not found.")
            if draft["status"]=="Attached": raise HTTPException(409,"This resume is already attached to another candidate.")
            resume_fields=json.loads(draft["parsed_json"]).get("fields",{})
            resume_text=resume_text or draft["resume_text"]
        name=p.name.strip() or str(resume_fields.get("name","")).strip()
        email=p.email.strip() or str(resume_fields.get("email","")).strip()
        location=p.location.strip() or str(resume_fields.get("location","")).strip()
        experience=p.experience if p.experience else (resume_fields.get("experience") or 0)
        skills=p.skills.strip() or ", ".join(resume_fields.get("skills") or [])
        phone=p.phone.strip() or str(resume_fields.get("phone",""))
        education=p.education.strip() or str(resume_fields.get("education",""))
        certifications=p.certifications.strip() or str(resume_fields.get("certifications",""))
        work_history=p.work_history.strip() or str(resume_fields.get("work_history",""))
        linkedin_url=p.linkedin_url.strip() or next((x for x in resume_fields.get("profile_links",[]) if "linkedin.com" in x.lower()),"")
        if not name: raise HTTPException(400,"Candidate name is required. Review the resume extraction or enter the name.")
        if (p.sourcing_task_id or "LinkedIn" in p.source_type) and not p.source_evidence.strip():
            raise HTTPException(400,"Add the profile or candidate evidence you reviewed before saving a LinkedIn-sourced candidate.")
        if p.employment_preference!="Unknown" and p.employment_preference_confirmed!="Candidate confirmed":
            raise HTTPException(400,"Only record W2/C2C or other engagement preferences after the candidate confirms them.")
        if p.work_auth!="Unknown" and p.work_auth_confirmed!="Candidate confirmed":
            raise HTTPException(400,"Only record OPT or other work authorization as confirmed when the candidate has confirmed it. Otherwise choose Unknown.")
        if p.c2c_status in ("Confirmed","Not available") and p.c2c_confirmed!="Candidate confirmed":
            raise HTTPException(400,"C2C status must be confirmed by the candidate before recording a yes or no.")
        if linkedin_url and not re.match(r"^https?://(www\.)?linkedin\.com/",linkedin_url,re.I):
            raise HTTPException(400,"Enter a valid LinkedIn profile URL.")
        source_url=p.source_url.strip() or linkedin_url
        if source_url and not re.match(r"^https?://",source_url,re.I):
            raise HTTPException(400,"Source URL must begin with http:// or https://.")
        if email and c.execute("SELECT id FROM candidates WHERE lower(email)=lower(?) AND email<>''",(email,)).fetchone():
            raise HTTPException(409,"Possible duplicate: a candidate with this email already exists.")
        if linkedin_url and c.execute("SELECT id FROM candidates WHERE lower(linkedin_url)=lower(?) AND linkedin_url<>''",(linkedin_url,)).fetchone():
            raise HTTPException(409,"Possible duplicate: this LinkedIn profile is already saved.")
        if p.sourcing_task_id:
            task=c.execute("SELECT id,status FROM sourcing_tasks WHERE id=?",(p.sourcing_task_id,)).fetchone()
            if not task: raise HTTPException(404,"Sourcing task not found.")
            if task["status"]=="Completed": raise HTTPException(409,"This sourcing task is completed. Reopen it before adding candidates.")
            if task["status"]=="Paused": raise HTTPException(409,"This sourcing task is paused. Resume it before adding candidates.")
        cur=c.execute("""INSERT INTO candidates(name,email,location,experience,skills,work_auth,c2c_status,linkedin_url,resume_text,created_at,open_to_work,availability_signal,profile_updated,source_type,source_url,source_evidence,c2c_confirmed,work_auth_confirmed,sourcing_task_id,phone,education,certifications,work_history,resume_draft_id,employment_preference,employment_preference_confirmed,contact_preference,do_not_contact)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (name,email,location,experience,skills,(p.work_auth if p.work_auth_confirmed=="Candidate confirmed" else "Unknown"),p.c2c_status,linkedin_url,resume_text,now(),p.open_to_work,p.availability_signal,p.profile_updated,p.source_type,source_url,p.source_evidence,p.c2c_confirmed,p.work_auth_confirmed,p.sourcing_task_id,phone,education,certifications,work_history,p.resume_draft_id,(p.employment_preference if p.employment_preference_confirmed=="Candidate confirmed" else "Unknown"),p.employment_preference_confirmed,p.contact_preference,int(p.do_not_contact)))
        candidate_id=cur.lastrowid
        if p.resume_draft_id:
            c.execute("UPDATE resume_drafts SET status='Attached',candidate_id=?,updated_at=? WHERE id=?",(candidate_id,now(),p.resume_draft_id))
        if p.sourcing_task_id:
            c.execute("UPDATE sourcing_tasks SET status=CASE WHEN status='Prepared' THEN 'In Progress' ELSE status END WHERE id=?",(p.sourcing_task_id,))
            c.execute("INSERT INTO sourcing_events(task_id,event_type,details,created_at) VALUES(?,?,?,?)",(p.sourcing_task_id,"Candidate captured","Candidate record #"+str(candidate_id),now()))
        return {"id":candidate_id,"message":"Candidate saved with reviewed resume" if p.resume_draft_id else ("Candidate saved with sourcing provenance" if p.sourcing_task_id else "Candidate saved")}
def build_plan(job_id, target_count=50):
    js=rows("SELECT * FROM jobs WHERE id=?",(job_id,))
    if not js: raise HTTPException(404,"Job not found")
    j=js[0]
    if not rows("SELECT id FROM job_versions WHERE job_id=? LIMIT 1",(job_id,)):
        raise HTTPException(409,"This requirement has not completed recruiter review and confirmation. Use the JD review workflow first.")
    if not isinstance(target_count,int) or target_count<50 or target_count>100:
        raise HTTPException(400,"Daily sourcing target must be between 50 and 100.")
    auth_terms=j.get("work_auth","")
    if auth_terms=="Unknown": auth_terms=""
    locations=[x.strip() for x in (j.get("location") or "").split(";") if x.strip()] or [""]
    skill_terms=tokens(j.get("skills",""))
    search_rows=[]
    for location in locations:
        variants=[
          ("Role", " ".join(x for x in [j["title"],location,"Open to Work"] if x)),
          ("Skills", " ".join(x for x in [j["title"],", ".join(skill_terms[:5]),location] if x))
        ]
        if auth_terms:
            variants.append(("Authorization hint"," ".join(x for x in [j["title"],location,auth_terms] if x)))
        seen=set()
        for search_type,query in variants:
            if not query or query.lower() in seen: continue
            seen.add(query.lower())
            url="https://www.linkedin.com/search/results/people/?keywords="+quote_plus(query)
            search_rows.append({"location":location or "All locations","search_type":search_type,"query":query,"linkedin_search_url":url})
    combined_query=" | ".join(x["query"] for x in search_rows)
    with db() as c:
        cur=c.execute("INSERT INTO sourcing_tasks(job_id,mode,query_text,linkedin_url,status,created_at,target_count) VALUES(?,?,?,?,?,?,?)",
          (job_id,"Location and keyword variants",combined_query,search_rows[0]["linkedin_search_url"],"Prepared",now(),target_count))
        task_id=cur.lastrowid
        for item in search_rows:
            c.execute("INSERT INTO sourcing_searches(task_id,location,search_type,query_text,linkedin_url,status,created_at) VALUES(?,?,?,?,?,?,?)",
              (task_id,item["location"],item["search_type"],item["query"],item["linkedin_search_url"],"Prepared",now()))
        c.execute("INSERT INTO sourcing_events(task_id,event_type,details,created_at) VALUES(?,?,?,?)",
          (task_id,"Plan prepared",str(len(search_rows))+" search variant(s); target "+str(target_count),now()))
    return {"task_id":task_id,"mode":"Recruiter-controlled location and keyword search plan","query":combined_query,
      "linkedin_search_url":search_rows[0]["linkedin_search_url"],"searches":search_rows,"target_count":target_count,
      "status":"Prepared","note":"Open each search in your authorized LinkedIn account. Recru Agent does not scrape LinkedIn or automatically collect profile data."}
@app.post("/api/jobs/{job_id}/sourcing-plan")
def sourcing_plan(job_id:int, payload:dict=None):
    target=int((payload or {}).get("target_count",50))
    return build_plan(job_id,target)
@app.get("/api/sourcing")
def sourcing_tasks():
    return rows("""SELECT s.*,j.title job_title,
      (SELECT COUNT(*) FROM candidates p WHERE p.sourcing_task_id=s.id) added_count
      FROM sourcing_tasks s JOIN jobs j ON j.id=s.job_id ORDER BY s.id DESC""")
@app.get("/api/sourcing/{task_id}/searches")
def sourcing_searches(task_id:int):
    if not rows("SELECT id FROM sourcing_tasks WHERE id=?",(task_id,)): raise HTTPException(404,"Sourcing task not found.")
    return rows("SELECT * FROM sourcing_searches WHERE task_id=? ORDER BY id",(task_id,))
@app.patch("/api/sourcing/searches/{search_id}")
def update_sourcing_search(search_id:int,payload:dict):
    search=rows("SELECT * FROM sourcing_searches WHERE id=?",(search_id,))
    if not search: raise HTTPException(404,"Sourcing search not found.")
    status=payload.get("status")
    if status not in ("Prepared","In Progress","Completed","Skipped"):
        raise HTTPException(400,"Search status must be Prepared, In Progress, Completed, or Skipped.")
    parent=rows("SELECT status FROM sourcing_tasks WHERE id=?",(search[0]["task_id"],))
    if parent and parent[0]["status"]=="Completed": raise HTTPException(409,"This sourcing task is completed. Reopen it before editing searches.")
    with db() as c:
        c.execute("UPDATE sourcing_searches SET status=? WHERE id=?",(status,search_id))
        if status=="In Progress":
            c.execute("UPDATE sourcing_tasks SET status='In Progress',started_at=CASE WHEN started_at='' THEN ? ELSE started_at END WHERE id=?",(now(),search[0]["task_id"]))
        c.execute("INSERT INTO sourcing_events(task_id,event_type,details,created_at) VALUES(?,?,?,?)",
          (search[0]["task_id"],"Location search updated",search[0]["location"]+": "+status,now()))
    return {"search_id":search_id,"status":status}
@app.get("/api/sourcing/{task_id}/activity")
def sourcing_activity(task_id:int):
    if not rows("SELECT id FROM sourcing_tasks WHERE id=?",(task_id,)): raise HTTPException(404,"Sourcing task not found.")
    return rows("SELECT * FROM sourcing_events WHERE task_id=? ORDER BY id DESC",(task_id,))
@app.patch("/api/sourcing/{task_id}")
def update_sourcing_task(task_id:int,payload:dict):
    task=rows("SELECT * FROM sourcing_tasks WHERE id=?",(task_id,))
    if not task: raise HTTPException(404,"Sourcing task not found.")
    status=payload.get("status",task[0]["status"])
    if status not in ("Prepared","In Progress","Paused","Completed"):
        raise HTTPException(400,"Status must be Prepared, In Progress, Paused, or Completed.")
    target=payload.get("target_count",task[0].get("target_count",50))
    if not isinstance(target,int) or target<50 or target>100:
        raise HTTPException(400,"Target must be between 50 and 100.")
    notes=str(payload.get("notes",task[0].get("notes","")))
    if status=="Completed":
        pending_searches=rows("SELECT id FROM sourcing_searches WHERE task_id=? AND status NOT IN ('Completed','Skipped')",(task_id,))
        if pending_searches: raise HTTPException(409,"Complete or skip every location search before completing the sourcing task.")
    started=task[0].get("started_at","") or (now() if status=="In Progress" else "")
    completed=now() if status=="Completed" else ""
    with db() as c:
        c.execute("UPDATE sourcing_tasks SET status=?,target_count=?,notes=?,started_at=?,completed_at=? WHERE id=?",
          (status,target,notes,started,completed,task_id))
        c.execute("INSERT INTO sourcing_events(task_id,event_type,details,created_at) VALUES(?,?,?,?)",
          (task_id,"Task updated","Status: "+status+"; target: "+str(target),now()))
    return {"task_id":task_id,"status":status,"target_count":target,"notes":notes}
@app.post("/api/jobs/upload")
async def upload_jd(file:UploadFile=File(...)):
    name=(file.filename or "").lower(); raw=await file.read()
    try:
        if name.endswith((".txt",".md")): text=raw.decode("utf-8",errors="replace")
        elif name.endswith(".pdf"):
            from pypdf import PdfReader
            reader=PdfReader(io.BytesIO(raw)); text="\n".join(p.extract_text() or "" for p in reader.pages)
        elif name.endswith(".docx"):
            from docx import Document
            doc=Document(io.BytesIO(raw)); text="\n".join(p.text for p in doc.paragraphs)
        else: raise HTTPException(415,"Upload a TXT, MD, PDF, or DOCX file.")
    except HTTPException: raise
    except Exception as e: raise HTTPException(400,"Could not read this file. If it is a scanned PDF, OCR is required.") from e
    if not text.strip(): raise HTTPException(400,"No readable text found in the file.")
    return extract_jd(text)
@app.post("/api/jobs/{job_id}/match")
def match(job_id:int):
    js=rows("SELECT * FROM jobs WHERE id=?",(job_id,))
    if not js: raise HTTPException(404,"Job not found")
    if not rows("SELECT id FROM job_versions WHERE job_id=? LIMIT 1",(job_id,)):
        raise HTTPException(409,"Confirm the job requirement before running candidate matching.")
    j=js[0]; required={x.lower() for x in tokens(j["skills"])}; preferred={x.lower() for x in tokens(j.get("preferred_skills",""))}
    out=[]
    for p in rows("SELECT * FROM candidates"):
        skills={x.lower() for x in tokens(p["skills"])}; matched=required&skills; pref=preferred&skills
        skill_score=round(65*len(matched)/len(required)) if required else 0
        required_exp=j.get("min_experience")
        exp_score=(15 if p["experience"]>=required_exp else round(15*p["experience"]/required_exp)) if required_exp is not None and required_exp>0 else 0
        loc_score=10 if not j["location"] or j["location"].lower() in p["location"].lower() else 0
        candidate_auth=p["work_auth"] if p.get("work_auth_confirmed")=="Candidate confirmed" else "Unknown"
        auth_match=bool(j["work_auth"]=="Unknown" or candidate_auth.lower()==j["work_auth"].lower() or j["work_auth"]=="Any US work authorization")
        auth_score=10 if auth_match and candidate_auth!="Unknown" else (5 if j["work_auth"]=="Unknown" else 0)
        candidate_view=dict(p); candidate_view["work_auth"]=candidate_auth
        base=min(100,skill_score+exp_score+loc_score+auth_score+min(5,len(pref)*2))
        otw=p.get("open_to_work","Unknown")
        priority={"Yes":10,"Actively looking":10,"Interested":6,"No":0,"Unknown":0}.get(otw,0)
        out.append({"candidate":candidate_view,"score":min(100,base+priority),"base_match":base,"availability_priority":priority,"matched_skills":sorted(matched),"preferred_matches":sorted(pref),"missing_skills":sorted(required-skills),"authorization_match":auth_match,"open_to_work":otw})
    return sorted(out,key=lambda x:(x["score"],x["base_match"]),reverse=True)
@app.post("/api/approvals")
def create_approval(payload:dict):
    with db() as c:
        if not c.execute("SELECT id FROM candidates WHERE id=?",(int(payload["candidate_id"]),)).fetchone(): raise HTTPException(404,"Candidate not found")
        if not c.execute("SELECT id FROM jobs WHERE id=?",(int(payload["job_id"]),)).fetchone(): raise HTTPException(404,"Job not found")
        cur=c.execute("INSERT INTO approvals(candidate_id,job_id,status,notes,created_at) VALUES(?,?, 'Pending',?,?)",(int(payload["candidate_id"]),int(payload["job_id"]),str(payload.get("notes","")),now()))
        return {"id":cur.lastrowid,"status":"Pending"}
@app.get("/api/approvals")
def get_approvals(): return rows("SELECT a.*,p.name candidate_name,j.title job_title FROM approvals a JOIN candidates p ON p.id=a.candidate_id JOIN jobs j ON j.id=a.job_id ORDER BY a.id DESC")
@app.patch("/api/approvals/{approval_id}")
def update_approval(approval_id:int,payload:dict):
    status=payload.get("status")
    if status not in ("Approved","Rejected"): raise HTTPException(400,"Status must be Approved or Rejected")
    with db() as c:
        cur=c.execute("UPDATE approvals SET status=?,notes=? WHERE id=?",(status,str(payload.get("notes","")),approval_id))
        if not cur.rowcount: raise HTTPException(404,"Approval not found")
    return {"id":approval_id,"status":status}
@app.get("/api/candidates/export")
def export_candidates():
    data=rows("SELECT * FROM candidates ORDER BY id")
    buf=io.StringIO(); fields=list(data[0].keys()) if data else ["id","name","email","location","experience","skills","work_auth","c2c_status","linkedin_url","open_to_work","availability_signal","source_type"]
    w=csv.DictWriter(buf,fieldnames=fields); w.writeheader(); w.writerows(data)
    return StreamingResponse(iter([buf.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=recru_agent_candidates.csv"})
app.mount("/static",StaticFiles(directory=ROOT/"static"),name="static")
@app.get("/",response_class=HTMLResponse)
def home(): return (ROOT/"static"/"index.html").read_text(encoding="utf-8")


# Milestone 1: reviewed JD drafts and recruiter confirmation.
from jd_intelligence import router as jd_router
from resume_intelligence import router as resume_router
from qualification import router as qualification_router
from communications import router as communications_router
from screening import router as screening_router
from advanced_matching import router as advanced_matching_router
from submissions import router as submissions_router
from interviews import router as interviews_router
app.include_router(jd_router)
app.include_router(resume_router)
app.include_router(qualification_router)
app.include_router(communications_router)
app.include_router(screening_router)
app.include_router(advanced_matching_router)
app.include_router(submissions_router)
app.include_router(interviews_router)
