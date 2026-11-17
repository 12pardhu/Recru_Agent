import os, sqlite3, json
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR",str(ROOT/"data")))
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/"recru_agent.db"
router=APIRouter(prefix="/api/submissions",tags=["Client Submission Management"])

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def stamp():
    return datetime.now(timezone.utc).isoformat()

def rows(sql,args=()):
    with connect() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]

def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS clients(
          id INTEGER PRIMARY KEY, company_name TEXT NOT NULL, contact_name TEXT DEFAULT '',
          email TEXT DEFAULT '', phone TEXT DEFAULT '', status TEXT DEFAULT 'Active',
          notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS client_submissions(
          id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL, candidate_id INTEGER NOT NULL,
          job_id INTEGER NOT NULL, screening_session_id INTEGER NOT NULL, qualification_id INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'Draft', submitted_rate TEXT DEFAULT '',
          recruiter_notes TEXT DEFAULT '', consent_snapshot TEXT NOT NULL DEFAULT 'Unknown',
          client_feedback TEXT DEFAULT '', feedback_status TEXT DEFAULT '',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, approved_at TEXT DEFAULT '', submitted_at TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS submission_events(
          id INTEGER PRIMARY KEY, submission_id INTEGER NOT NULL, event_type TEXT NOT NULL,
          details TEXT DEFAULT '', created_at TEXT NOT NULL
        );
        """)
init()

def verify_readiness(candidate_id,job_id,screening_session_id):
    sessions=rows("SELECT * FROM screening_sessions WHERE id=? AND candidate_id=? AND job_id=?",(screening_session_id,candidate_id,job_id))
    if not sessions: raise HTTPException(404,"Matching screening session not found.")
    session=sessions[0]
    if session["status"]!="Completed": raise HTTPException(409,"Complete recruiter screening before client submission.")
    if session["submission_consent"]!="Yes": raise HTTPException(409,"Explicit candidate consent to submit this profile to this client/role is required.")
    quals=rows("""SELECT * FROM qualification_records WHERE candidate_id=? AND job_id=?
      ORDER BY id DESC LIMIT 1""",(candidate_id,job_id))
    if not quals or quals[0]["recruiter_decision"]!="Proceed to Client Submission":
        raise HTTPException(409,"Recruiter qualification decision must be 'Proceed to Client Submission' before creating a submission.")
    candidates=rows("SELECT do_not_contact FROM candidates WHERE id=?",(candidate_id,))
    if not candidates: raise HTTPException(404,"Candidate not found.")
    if candidates[0].get("do_not_contact"):
        raise HTTPException(409,"Candidate is marked Do not contact. Review the contact restriction before proceeding.")
    return session,quals[0]

@router.get("/clients")
def list_clients():
    return rows("SELECT * FROM clients ORDER BY company_name")

@router.post("/clients")
def create_client(payload:dict):
    name=str(payload.get("company_name","")).strip()
    if not name: raise HTTPException(400,"Client company name is required.")
    email=str(payload.get("email","")).strip()
    with connect() as c:
        cur=c.execute("INSERT INTO clients(company_name,contact_name,email,phone,status,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
          (name,str(payload.get("contact_name","")),email,str(payload.get("phone","")),str(payload.get("status","Active")),str(payload.get("notes","")),stamp(),stamp()))
    return {"id":cur.lastrowid,"message":"Client saved."}

@router.patch("/clients/{client_id}")
def update_client(client_id:int,payload:dict):
    clients=rows("SELECT * FROM clients WHERE id=?",(client_id,))
    if not clients: raise HTTPException(404,"Client not found.")
    status=payload.get("status",clients[0]["status"])
    if status not in ("Active","Inactive"): raise HTTPException(400,"Client status must be Active or Inactive.")
    with connect() as c:
        c.execute("UPDATE clients SET company_name=?,contact_name=?,email=?,phone=?,status=?,notes=?,updated_at=? WHERE id=?",
          (str(payload.get("company_name",clients[0]["company_name"])).strip(),str(payload.get("contact_name",clients[0]["contact_name"])),
           str(payload.get("email",clients[0]["email"])),str(payload.get("phone",clients[0]["phone"])),status,
           str(payload.get("notes",clients[0]["notes"])),stamp(),client_id))
    return {"id":client_id,"message":"Client updated."}

@router.post("/drafts")
def create_submission_draft(payload:dict):
    client_id=int(payload.get("client_id") or 0)
    candidate_id=int(payload.get("candidate_id") or 0)
    job_id=int(payload.get("job_id") or 0)
    screening_id=int(payload.get("screening_session_id") or 0)
    clients=rows("SELECT * FROM clients WHERE id=? AND status='Active'",(client_id,))
    if not clients: raise HTTPException(404,"Active client not found.")
    jobs=rows("SELECT id FROM jobs WHERE id=?",(job_id,))
    if not jobs: raise HTTPException(404,"Job requirement not found.")
    if not rows("SELECT id FROM job_versions WHERE job_id=? LIMIT 1",(job_id,)):
        raise HTTPException(409,"Only confirmed job requirements can be submitted.")
    session,qualification=verify_readiness(candidate_id,job_id,screening_id)
    existing=rows("""SELECT id,status FROM client_submissions WHERE client_id=? AND candidate_id=? AND job_id=?
      AND status NOT IN ('Withdrawn','Rejected')""",(client_id,candidate_id,job_id))
    if existing: raise HTTPException(409,"A non-withdrawn submission already exists for this candidate, client, and job.")
    with connect() as c:
        cur=c.execute("""INSERT INTO client_submissions(client_id,candidate_id,job_id,screening_session_id,qualification_id,status,submitted_rate,recruiter_notes,consent_snapshot,created_at,updated_at)
          VALUES(?,?,?,?,?,'Draft',?,?, 'Yes',?,?)""",
          (client_id,candidate_id,job_id,screening_id,qualification["id"],str(payload.get("submitted_rate","")),str(payload.get("recruiter_notes","")),stamp(),stamp()))
        sid=cur.lastrowid
        c.execute("INSERT INTO submission_events(submission_id,event_type,details,created_at) VALUES(?,?,?,?)",(sid,"Submission draft created","Candidate consent verified; awaiting recruiter review.",stamp()))
    return {"id":sid,"status":"Draft","message":"Submission draft created. No client submission has been sent."}

@router.get("")
def list_submissions():
    return rows("""SELECT s.*,cl.company_name,c.name candidate_name,j.title job_title
      FROM client_submissions s JOIN clients cl ON cl.id=s.client_id
      JOIN candidates c ON c.id=s.candidate_id JOIN jobs j ON j.id=s.job_id
      ORDER BY s.id DESC""")

@router.get("/{submission_id}")
def get_submission(submission_id:int):
    data=rows("""SELECT s.*,cl.company_name,cl.contact_name,c.name candidate_name,c.email candidate_email,
      j.title job_title FROM client_submissions s JOIN clients cl ON cl.id=s.client_id
      JOIN candidates c ON c.id=s.candidate_id JOIN jobs j ON j.id=s.job_id WHERE s.id=?""",(submission_id,))
    if not data: raise HTTPException(404,"Submission not found.")
    data[0]["events"]=rows("SELECT * FROM submission_events WHERE submission_id=? ORDER BY id DESC",(submission_id,))
    return data[0]

@router.patch("/{submission_id}")
def edit_submission(submission_id:int,payload:dict):
    data=rows("SELECT * FROM client_submissions WHERE id=?",(submission_id,))
    if not data: raise HTTPException(404,"Submission not found.")
    if data[0]["status"]!="Draft": raise HTTPException(409,"Only draft submissions can be edited.")
    with connect() as c:
        c.execute("UPDATE client_submissions SET submitted_rate=?,recruiter_notes=?,updated_at=? WHERE id=?",
          (str(payload.get("submitted_rate",data[0]["submitted_rate"])),str(payload.get("recruiter_notes",data[0]["recruiter_notes"])),stamp(),submission_id))
        c.execute("INSERT INTO submission_events(submission_id,event_type,details,created_at) VALUES(?,?,?,?)",(submission_id,"Draft edited","Rate or recruiter notes updated.",stamp()))
    return {"id":submission_id,"message":"Submission draft updated."}

@router.post("/{submission_id}/approve")
def approve_submission(submission_id:int,payload:dict):
    data=rows("SELECT * FROM client_submissions WHERE id=?",(submission_id,))
    if not data: raise HTTPException(404,"Submission not found.")
    s=data[0]
    if s["status"]!="Draft": raise HTTPException(409,"Only a draft submission can be approved.")
    verify_readiness(s["candidate_id"],s["job_id"],s["screening_session_id"])
    approver=str(payload.get("approver","Recruiter")).strip() or "Recruiter"
    with connect() as c:
        c.execute("UPDATE client_submissions SET status='Approved',approved_at=?,updated_at=? WHERE id=?",(stamp(),stamp(),submission_id))
        c.execute("INSERT INTO submission_events(submission_id,event_type,details,created_at) VALUES(?,?,?,?)",(submission_id,"Submission approved","Approved by "+approver+". Not yet sent to client.",stamp()))
    return {"id":submission_id,"status":"Approved","message":"Submission approved internally. It has not been sent to the client."}

@router.post("/{submission_id}/mark-manually-submitted")
def mark_manually_submitted(submission_id:int,payload:dict):
    if not payload.get("confirmed_manual_submission"): raise HTTPException(400,"Confirm that you manually submitted this profile to the client.")
    data=rows("SELECT * FROM client_submissions WHERE id=?",(submission_id,))
    if not data: raise HTTPException(404,"Submission not found.")
    s=data[0]
    if s["status"]!="Approved": raise HTTPException(409,"Only an internally approved submission can be marked manually submitted.")
    verify_readiness(s["candidate_id"],s["job_id"],s["screening_session_id"])
    with connect() as c:
        c.execute("UPDATE client_submissions SET status='Manually Submitted',submitted_at=?,updated_at=? WHERE id=?",(stamp(),stamp(),submission_id))
        c.execute("INSERT INTO submission_events(submission_id,event_type,details,created_at) VALUES(?,?,?,?)",(submission_id,"Marked manually submitted","Recruiter confirmed manual client submission.",stamp()))
    return {"id":submission_id,"status":"Manually Submitted","message":"Manual client submission recorded. Recru Agent did not send any data."}

@router.post("/{submission_id}/feedback")
def record_client_feedback(submission_id:int,payload:dict):
    data=rows("SELECT status FROM client_submissions WHERE id=?",(submission_id,))
    if not data: raise HTTPException(404,"Submission not found.")
    if data[0]["status"] not in ("Manually Submitted","Client Feedback"): raise HTTPException(409,"Client feedback can be recorded only after manual submission.")
    feedback_status=payload.get("feedback_status")
    allowed=("Interview Requested","Rejected","On Hold","More Information Requested","Offer","No Update")
    if feedback_status not in allowed: raise HTTPException(400,"Choose a valid client feedback status.")
    feedback=str(payload.get("client_feedback",""))
    with connect() as c:
        c.execute("UPDATE client_submissions SET status='Client Feedback',feedback_status=?,client_feedback=?,updated_at=? WHERE id=?",
          (feedback_status,feedback,stamp(),submission_id))
        c.execute("INSERT INTO submission_events(submission_id,event_type,details,created_at) VALUES(?,?,?,?)",(submission_id,"Client feedback recorded",feedback_status+" · "+feedback,stamp()))
    return {"id":submission_id,"status":"Client Feedback","feedback_status":feedback_status}

@router.post("/{submission_id}/withdraw")
def withdraw_submission(submission_id:int):
    data=rows("SELECT status FROM client_submissions WHERE id=?",(submission_id,))
    if not data: raise HTTPException(404,"Submission not found.")
    if data[0]["status"] in ("Withdrawn","Rejected"): raise HTTPException(409,"Submission is already closed.")
    with connect() as c:
        c.execute("UPDATE client_submissions SET status='Withdrawn',updated_at=? WHERE id=?",(stamp(),submission_id))
        c.execute("INSERT INTO submission_events(submission_id,event_type,details,created_at) VALUES(?,?,?,?)",(submission_id,"Withdrawn","Recruiter withdrew the submission.",stamp()))
    return {"id":submission_id,"status":"Withdrawn"}

@router.get("/{submission_id}/history")
def submission_history(submission_id:int):
    if not rows("SELECT id FROM client_submissions WHERE id=?",(submission_id,)):
        raise HTTPException(404,"Submission not found.")
    return rows("SELECT * FROM submission_events WHERE submission_id=? ORDER BY id DESC",(submission_id,))
