import json, os, re, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR",str(ROOT/"data")))
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/"recru_agent.db"
router=APIRouter(prefix="/api/screening",tags=["OPT Recruiter Screening"])

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def stamp():
    return datetime.now(timezone.utc).isoformat()

def rows(sql,args=()):
    with connect() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]

QUESTIONS=[
 ("current_work_authorization","Work authorization","What is your current US work authorization? Please state the category in your own words."),
 ("opt_start_date","OPT / EAD dates","If applicable, what is the EAD start date?"),
 ("ead_expiry_date","OPT / EAD dates","If applicable, what is the EAD expiration date?"),
 ("stem_opt_status","STEM OPT","Are you currently on STEM OPT, or do you expect to apply for STEM OPT?"),
 ("stem_opt_end_date","STEM OPT","If applicable, what is the STEM OPT end date?"),
 ("sponsorship_required","Sponsorship","Will you require employer sponsorship now or in the future?"),
 ("c2c_availability","Engagement type","Are you able to work on C2C?"),
 ("employment_preference","Engagement type","Which engagement types do you accept (C2C, W2, both, full-time, or another arrangement)?"),
 ("years_experience","Experience","How many years of total professional experience do you have?"),
 ("current_location","Location","What is your current city and state?"),
 ("work_arrangement","Work arrangement","Are you open to onsite, hybrid, remote, relocation, or travel for this role?"),
 ("expected_rate","Compensation","What is your expected hourly rate or salary range, and is it W2 or C2C?"),
 ("availability","Availability","When could you start, and are you actively considering new opportunities?"),
 ("interview_availability","Interview","What days or time windows are convenient for an interview?"),
 ("candidate_consent_to_submit","Client submission consent","Do you authorize us to present your profile to this client for this specific role?")
]

def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS screening_sessions(
          id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL, job_id INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'Draft', scheduled_at TEXT DEFAULT '',
          recruiter_notes TEXT DEFAULT '', submission_consent TEXT NOT NULL DEFAULT 'Unknown',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS screening_answers(
          id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, question_key TEXT NOT NULL,
          category TEXT NOT NULL, question TEXT NOT NULL, answer TEXT DEFAULT '',
          confirmation_status TEXT NOT NULL DEFAULT 'Unknown', evidence TEXT DEFAULT '',
          updated_at TEXT NOT NULL, UNIQUE(session_id,question_key)
        );
        CREATE TABLE IF NOT EXISTS screening_events(
          id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, event_type TEXT NOT NULL,
          details TEXT DEFAULT '', created_at TEXT NOT NULL
        );
        """)
init()

class AnswerUpdate(BaseModel):
    answer: str = ""
    confirmation_status: str = "Unknown"
    evidence: str = ""

@router.get("/questions")
def get_questions():
    return [{"question_key":k,"category":cat,"question":q} for k,cat,q in QUESTIONS]

@router.post("/sessions")
def create_session(payload:dict):
    candidate_id=int(payload.get("candidate_id") or 0); job_id=int(payload.get("job_id") or 0)
    candidate=rows("SELECT id FROM candidates WHERE id=?",(candidate_id,))
    job=rows("SELECT id FROM jobs WHERE id=?",(job_id,))
    if not candidate: raise HTTPException(404,"Candidate not found.")
    if not job: raise HTTPException(404,"Job requirement not found.")
    if not rows("SELECT id FROM job_versions WHERE job_id=? LIMIT 1",(job_id,)):
        raise HTTPException(409,"Confirm the job requirement before starting recruiter screening.")
    with connect() as c:
        cur=c.execute("INSERT INTO screening_sessions(candidate_id,job_id,status,scheduled_at,recruiter_notes,submission_consent,created_at,updated_at) VALUES(?,?,'Draft',?,'','Unknown',?,?)",
          (candidate_id,job_id,str(payload.get("scheduled_at","")),stamp(),stamp()))
        sid=cur.lastrowid
        for key,category,question in QUESTIONS:
            c.execute("INSERT INTO screening_answers(session_id,question_key,category,question,answer,confirmation_status,evidence,updated_at) VALUES(?,?,?,?,?,'Unknown','',?)",
              (sid,key,category,question,"",stamp()))
        c.execute("INSERT INTO screening_events(session_id,event_type,details,created_at) VALUES(?,?,?,?)",(sid,"Screening created","Draft screening session created.",stamp()))
    return {"id":sid,"status":"Draft","message":"Screening session created. Record candidate answers and confirmation evidence."}

@router.get("/sessions")
def list_sessions():
    return rows("""SELECT s.*,c.name candidate_name,j.title job_title
      FROM screening_sessions s JOIN candidates c ON c.id=s.candidate_id
      JOIN jobs j ON j.id=s.job_id ORDER BY s.id DESC""")

@router.get("/sessions/{session_id}")
def get_session(session_id:int):
    data=rows("""SELECT s.*,c.name candidate_name,c.email candidate_email,j.title job_title
      FROM screening_sessions s JOIN candidates c ON c.id=s.candidate_id
      JOIN jobs j ON j.id=s.job_id WHERE s.id=?""",(session_id,))
    if not data: raise HTTPException(404,"Screening session not found.")
    data[0]["answers"]=rows("SELECT * FROM screening_answers WHERE session_id=? ORDER BY id",(session_id,))
    data[0]["events"]=rows("SELECT * FROM screening_events WHERE session_id=? ORDER BY id DESC",(session_id,))
    return data[0]

@router.patch("/sessions/{session_id}/answers/{question_key}")
def update_answer(session_id:int,question_key:str,payload:AnswerUpdate):
    if question_key not in {x[0] for x in QUESTIONS}: raise HTTPException(404,"Screening question not found.")
    if payload.confirmation_status not in ("Unknown","Candidate confirmed","Not confirmed"):
        raise HTTPException(400,"Confirmation status must be Unknown, Candidate confirmed, or Not confirmed.")
    with connect() as c:
        cur=c.execute("UPDATE screening_answers SET answer=?,confirmation_status=?,evidence=?,updated_at=? WHERE session_id=? AND question_key=?",
          (payload.answer,payload.confirmation_status,payload.evidence,stamp(),session_id,question_key))
        if not cur.rowcount: raise HTTPException(404,"Screening answer not found.")
        c.execute("INSERT INTO screening_events(session_id,event_type,details,created_at) VALUES(?,?,?,?)",(session_id,"Answer updated",question_key+" · "+payload.confirmation_status,stamp()))
    return {"session_id":session_id,"question_key":question_key,"message":"Screening answer saved."}

@router.patch("/sessions/{session_id}")
def update_session(session_id:int,payload:dict):
    sessions=rows("SELECT * FROM screening_sessions WHERE id=?",(session_id,))
    if not sessions: raise HTTPException(404,"Screening session not found.")
    status=payload.get("status",sessions[0]["status"])
    if status not in ("Draft","Scheduled","In Progress","Completed","Cancelled"):
        raise HTTPException(400,"Invalid screening status.")
    consent=payload.get("submission_consent",sessions[0]["submission_consent"])
    if consent not in ("Unknown","Yes","No"): raise HTTPException(400,"Submission consent must be Unknown, Yes, or No.")
    scheduled=str(payload.get("scheduled_at",sessions[0]["scheduled_at"]))
    notes=str(payload.get("recruiter_notes",sessions[0]["recruiter_notes"]))
    completed=stamp() if status=="Completed" else ""
    with connect() as c:
        c.execute("UPDATE screening_sessions SET status=?,scheduled_at=?,recruiter_notes=?,submission_consent=?,updated_at=?,completed_at=? WHERE id=?",
          (status,scheduled,notes,consent,stamp(),completed,session_id))
        c.execute("INSERT INTO screening_events(session_id,event_type,details,created_at) VALUES(?,?,?,?)",(session_id,"Session updated","Status: "+status+"; submission consent: "+consent,stamp()))
    return {"id":session_id,"status":status,"submission_consent":consent}

@router.post("/sessions/{session_id}/apply-confirmed")
def apply_confirmed_answers(session_id:int):
    session=rows("SELECT * FROM screening_sessions WHERE id=?",(session_id,))
    if not session: raise HTTPException(404,"Screening session not found.")
    answers={x["question_key"]:x for x in rows("SELECT * FROM screening_answers WHERE session_id=?",(session_id,))}
    updates={}
    def confirmed(key):
        a=answers.get(key); return a and a["confirmation_status"]=="Candidate confirmed" and a["answer"].strip()
    auth=answers.get("current_work_authorization")
    allowed_auth=("OPT","STEM OPT","H-1B","Green Card","US Citizen","EAD")
    if confirmed("current_work_authorization"):
        value=auth["answer"].strip()
        if value in allowed_auth:
            updates["work_auth"]=value; updates["work_auth_confirmed"]="Candidate confirmed"
    if confirmed("c2c_availability"):
        value=answers["c2c_availability"]["answer"].strip().lower()
        if value in ("yes","available"):
            updates["c2c_status"]="Confirmed"; updates["c2c_confirmed"]="Candidate confirmed"
        elif value in ("no","not available"):
            updates["c2c_status"]="Not available"; updates["c2c_confirmed"]="Candidate confirmed"
    if confirmed("employment_preference"):
        value=answers["employment_preference"]["answer"].strip()
        if value in ("C2C","W2","Both","Full-time","Contract","1099"):
            updates["employment_preference"]=value; updates["employment_preference_confirmed"]="Candidate confirmed"
    if confirmed("current_location"):
        updates["location"]=answers["current_location"]["answer"].strip()
    if confirmed("years_experience"):
        try:
            years=float(answers["years_experience"]["answer"].strip())
            if years>=0: updates["experience"]=years
        except ValueError: pass
    if confirmed("availability"):
        value=answers["availability"]["answer"].strip()
        if value: updates["availability_signal"]="Actively looking" if "actively looking" in value.lower() else "Interested"
    consent=answers.get("candidate_consent_to_submit")
    submission_consent="Unknown"
    if confirmed("candidate_consent_to_submit"):
        value=consent["answer"].strip().lower()
        if value in ("yes","no"): submission_consent=value.capitalize()
    if updates:
        sets=", ".join(k+"=?" for k in updates)
        with connect() as c:
            c.execute("UPDATE candidates SET "+sets+" WHERE id=?",( *updates.values(),session[0]["candidate_id"]))
    with connect() as c:
        c.execute("UPDATE screening_sessions SET submission_consent=?,updated_at=? WHERE id=?",(submission_consent,stamp(),session_id))
        c.execute("INSERT INTO screening_events(session_id,event_type,details,created_at) VALUES(?,?,?,?)",(session_id,"Confirmed answers applied","Updated candidate fields: "+", ".join(updates.keys())+"; submission consent: "+submission_consent,stamp()))
    return {"session_id":session_id,"updated_candidate_fields":list(updates.keys()),"submission_consent":submission_consent,
      "message":"Only candidate-confirmed answers were applied. Review the candidate record before proceeding."}

@router.get("/sessions/{session_id}/history")
def screening_history(session_id:int):
    if not rows("SELECT id FROM screening_sessions WHERE id=?",(session_id,)):
        raise HTTPException(404,"Screening session not found.")
    return rows("SELECT * FROM screening_events WHERE session_id=? ORDER BY id DESC",(session_id,))
