import os, sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from auth import require_admin

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR",str(ROOT/"data")))
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/"recru_agent.db"
RESUME_DOCS=DATA/"resume_documents"
router=APIRouter(prefix="/api/privacy",tags=["Privacy and Retention"])

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def stamp():
    return datetime.now(timezone.utc).isoformat()

def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS privacy_settings(
          id INTEGER PRIMARY KEY CHECK(id=1), candidate_retention_days INTEGER,
          updated_by TEXT DEFAULT '', updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS privacy_requests(
          id INTEGER PRIMARY KEY, candidate_id INTEGER, request_type TEXT NOT NULL,
          reason TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'Pending',
          created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          resolved_by TEXT DEFAULT '', resolution_notes TEXT DEFAULT ''
        );
        """)
        c.execute("INSERT OR IGNORE INTO privacy_settings(id,candidate_retention_days,updated_by,updated_at) VALUES(1,NULL,'',?)",(stamp(),))
init()

class RetentionUpdate(BaseModel):
    candidate_retention_days:int=Field(ge=30,le=3650)

class PrivacyRequestCreate(BaseModel):
    candidate_id:int=Field(gt=0)
    request_type:str
    reason:str=Field(min_length=3,max_length=1000)

class PrivacyRequestUpdate(BaseModel):
    status:str
    resolution_notes:str=""

class PurgeConfirm(BaseModel):
    confirm:bool=False

def erase_candidate(candidate_id:int, reason:str):
    paths=[]
    with connect() as c:
        candidate=c.execute("SELECT * FROM candidates WHERE id=?",(candidate_id,)).fetchone()
        if not candidate: raise HTTPException(404,"Candidate not found.")
        resume_ids=set()
        if candidate["resume_draft_id"]: resume_ids.add(candidate["resume_draft_id"])
        resume_rows=c.execute("SELECT id,stored_path FROM resume_drafts WHERE candidate_id=?",(candidate_id,)).fetchall()
        for row in resume_rows:
            resume_ids.add(row["id"])
            if row["stored_path"]: paths.append(row["stored_path"])
        if candidate["sourcing_task_id"]:
            c.execute("UPDATE sourcing_events SET details='Candidate record removed for privacy' WHERE task_id=? AND details LIKE ?",
              (candidate["sourcing_task_id"],"%Candidate record #"+str(candidate_id)+"%"))
        submission_rows=c.execute("SELECT id FROM client_submissions WHERE candidate_id=?",(candidate_id,)).fetchall()
        submission_ids=[r["id"] for r in submission_rows]
        if submission_ids:
            marks=",".join("?" for _ in submission_ids)
            interview_rows=c.execute("SELECT id FROM interviews WHERE submission_id IN ("+marks+")",submission_ids).fetchall()
            interview_ids=[r["id"] for r in interview_rows]
            if interview_ids:
                imarks=",".join("?" for _ in interview_ids)
                c.execute("DELETE FROM interview_events WHERE interview_id IN ("+imarks+")",interview_ids)
                c.execute("DELETE FROM interviews WHERE id IN ("+imarks+")",interview_ids)
            c.execute("DELETE FROM submission_events WHERE submission_id IN ("+marks+")",submission_ids)
            c.execute("DELETE FROM client_submissions WHERE id IN ("+marks+")",submission_ids)
        screening_rows=c.execute("SELECT id FROM screening_sessions WHERE candidate_id=?",(candidate_id,)).fetchall()
        screening_ids=[r["id"] for r in screening_rows]
        if screening_ids:
            marks=",".join("?" for _ in screening_ids)
            c.execute("DELETE FROM screening_answers WHERE session_id IN ("+marks+")",screening_ids)
            c.execute("DELETE FROM screening_events WHERE session_id IN ("+marks+")",screening_ids)
            c.execute("DELETE FROM screening_sessions WHERE id IN ("+marks+")",screening_ids)
        qualification_rows=c.execute("SELECT id FROM qualification_records WHERE candidate_id=?",(candidate_id,)).fetchall()
        qualification_ids=[r["id"] for r in qualification_rows]
        if qualification_ids:
            marks=",".join("?" for _ in qualification_ids)
            c.execute("DELETE FROM qualification_events WHERE record_id IN ("+marks+")",qualification_ids)
            c.execute("DELETE FROM qualification_records WHERE id IN ("+marks+")",qualification_ids)
        message_rows=c.execute("SELECT id FROM communication_messages WHERE candidate_id=?",(candidate_id,)).fetchall()
        message_ids=[r["id"] for r in message_rows]
        if message_ids:
            marks=",".join("?" for _ in message_ids)
            c.execute("DELETE FROM communication_events WHERE message_id IN ("+marks+")",message_ids)
            c.execute("DELETE FROM communication_messages WHERE id IN ("+marks+")",message_ids)
        pipeline_rows=c.execute("SELECT id FROM recruitment_pipeline WHERE candidate_id=?",(candidate_id,)).fetchall()
        pipeline_ids=[r["id"] for r in pipeline_rows]
        if pipeline_ids:
            marks=",".join("?" for _ in pipeline_ids)
            c.execute("DELETE FROM pipeline_events WHERE pipeline_id IN ("+marks+")",pipeline_ids)
            c.execute("DELETE FROM recruitment_pipeline WHERE id IN ("+marks+")",pipeline_ids)
        # Remove candidate-specific matching snapshots as they may contain copied profile evidence in result_json.
        c.execute("DELETE FROM match_results WHERE candidate_id=?",(candidate_id,))
        c.execute("DELETE FROM approvals WHERE candidate_id=?",(candidate_id,))
        if resume_ids:
            marks=",".join("?" for _ in resume_ids)
            c.execute("DELETE FROM resume_drafts WHERE id IN ("+marks+")",list(resume_ids))
        c.execute("UPDATE privacy_requests SET candidate_id=NULL,updated_at=?,resolution_notes=CASE WHEN resolution_notes='' THEN ? ELSE resolution_notes END WHERE candidate_id=?",
          (stamp(),"Candidate data erased.",candidate_id))
        c.execute("DELETE FROM candidates WHERE id=?",(candidate_id,))
    for raw in paths:
        try:
            path=Path(raw).resolve()
            if RESUME_DOCS.resolve() in path.parents and path.is_file(): path.unlink()
        except OSError:
            pass
    return {"candidate_id":candidate_id,"erased":True,"reason":reason,"message":"Candidate record and linked workflow records were erased. The deletion action should be retained in your organization's separate compliance records."}

@router.get("/requests")
def list_requests(request:Request):
    require_admin(request)
    with connect() as c:
        data=c.execute("SELECT * FROM privacy_requests ORDER BY created_at DESC").fetchall()
    return [dict(x) for x in data]

@router.post("/requests")
def create_request(payload:PrivacyRequestCreate,request:Request):
    require_admin(request)
    if payload.request_type not in ("Access","Correction","Deletion"):
        raise HTTPException(400,"Request type must be Access, Correction, or Deletion.")
    with connect() as c:
        if not c.execute("SELECT id FROM candidates WHERE id=?",(payload.candidate_id,)).fetchone():
            raise HTTPException(404,"Candidate not found.")
        cur=c.execute("INSERT INTO privacy_requests(candidate_id,request_type,reason,status,created_by,created_at,updated_at) VALUES(?,?,?,'Pending',?,?,?)",
          (payload.candidate_id,payload.request_type,payload.reason,request.state.user["username"],stamp(),stamp()))
    return {"id":cur.lastrowid,"status":"Pending","message":"Privacy request recorded."}

@router.patch("/requests/{request_id}")
def update_request(request_id:int,payload:PrivacyRequestUpdate,request:Request):
    require_admin(request)
    if payload.status not in ("Pending","In Review","Approved","Rejected","Completed"):
        raise HTTPException(400,"Choose Pending, In Review, Approved, or Rejected. Deletion requests are completed only after the erase action.")
    with connect() as c:
        row=c.execute("SELECT id,request_type FROM privacy_requests WHERE id=?",(request_id,)).fetchone()
        if not row: raise HTTPException(404,"Privacy request not found.")
        if row["request_type"]=="Deletion" and payload.status=="Completed": raise HTTPException(409,"Deletion requests can be completed only through the approved erase action.")
        c.execute("UPDATE privacy_requests SET status=?,updated_at=?,resolved_by=?,resolution_notes=? WHERE id=?",
          (payload.status,stamp(),request.state.user["username"],payload.resolution_notes,request_id))
    return {"id":request_id,"status":payload.status}

@router.post("/requests/{request_id}/erase")
def process_deletion_request(request_id:int,request:Request):
    require_admin(request)
    with connect() as c:
        row=c.execute("SELECT * FROM privacy_requests WHERE id=?",(request_id,)).fetchone()
    if not row: raise HTTPException(404,"Privacy request not found.")
    if row["request_type"]!="Deletion" or row["status"]!="Approved":
        raise HTTPException(409,"Only an approved deletion request can be processed.")
    if row["candidate_id"] is None: raise HTTPException(404,"Candidate data has already been erased.")
    result=erase_candidate(row["candidate_id"],"Approved privacy deletion request #"+str(request_id))
    with connect() as c:
        c.execute("UPDATE privacy_requests SET candidate_id=NULL,status='Completed',updated_at=?,resolved_by=?,resolution_notes='Candidate and linked workflow records erased.' WHERE id=?",
          (stamp(),request.state.user["username"],request_id))
    return result

@router.get("/retention")
def get_retention(request:Request):
    require_admin(request)
    with connect() as c: row=c.execute("SELECT * FROM privacy_settings WHERE id=1").fetchone()
    return dict(row) if row else {"candidate_retention_days":None}

@router.put("/retention")
def set_retention(payload:RetentionUpdate,request:Request):
    require_admin(request)
    with connect() as c:
        c.execute("UPDATE privacy_settings SET candidate_retention_days=?,updated_by=?,updated_at=? WHERE id=1",
          (payload.candidate_retention_days,request.state.user["username"],stamp()))
    return {"candidate_retention_days":payload.candidate_retention_days,"message":"Retention period saved. Records are not automatically deleted; an administrator must review and run the purge."}

@router.post("/retention/preview")
def retention_preview(request:Request):
    require_admin(request)
    with connect() as c: row=c.execute("SELECT candidate_retention_days FROM privacy_settings WHERE id=1").fetchone()
    days=row["candidate_retention_days"] if row else None
    if not days: raise HTTPException(409,"Set a candidate retention period before previewing a purge.")
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
    with connect() as c:
        count=c.execute("SELECT COUNT(*) FROM candidates WHERE created_at<?",(cutoff,)).fetchone()[0]
        sample=c.execute("SELECT id,created_at FROM candidates WHERE created_at<? ORDER BY created_at LIMIT 25",(cutoff,)).fetchall()
    return {"retention_days":days,"cutoff":cutoff,"candidate_count":count,"sample":[dict(x) for x in sample],"requires_explicit_confirmation":True}

@router.post("/retention/purge")
def retention_purge(payload:PurgeConfirm,request:Request):
    require_admin(request)
    if not payload.confirm: raise HTTPException(400,"Explicit confirmation is required to erase records beyond the retention period.")
    preview=retention_preview(request)
    ids=[x["id"] for x in preview["sample"]]
    # Process in bounded batches; a second preview/purge handles any remaining records.
    erased=[]
    for candidate_id in ids:
        erased.append(erase_candidate(candidate_id,"Retention period of "+str(preview["retention_days"])+" days elapsed"))
    return {"erased_count":len(erased),"remaining_candidate_count":max(0,preview["candidate_count"]-len(erased)),"message":"Retention purge completed for the first batch. Review the remaining count and run again if needed."}
