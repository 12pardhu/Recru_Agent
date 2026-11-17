import os, sqlite3, re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
from fastapi import APIRouter, HTTPException

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR",str(ROOT/"data")))
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/"recru_agent.db"
router=APIRouter(prefix="/api/interviews",tags=["Interview Management"])

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def stamp():
    return datetime.now(timezone.utc).isoformat()

def rows(sql,args=()):
    with connect() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]


def validate_schedule(value, timezone_name):
    raw = str(value or "").strip()
    if not raw:
        raise HTTPException(400,"Interview date and time are required.")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError:
        raise HTTPException(400,"Enter a valid date and time, for example 2026-11-20T14:30.")
    if parsed.date() < datetime.now().date():
        raise HTTPException(400,"Interview date cannot be in the past.")
    zone = str(timezone_name or "").strip()
    if not zone:
        raise HTTPException(400,"Select the interview time zone.")
    try:
        ZoneInfo(zone)
    except ZoneInfoNotFoundError:
        raise HTTPException(400,"Use a valid IANA time zone such as America/Chicago or America/New_York.")
    return raw, zone

def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS interviews(
          id INTEGER PRIMARY KEY, submission_id INTEGER NOT NULL, round_number INTEGER NOT NULL DEFAULT 1,
          round_name TEXT DEFAULT 'Technical', scheduled_at TEXT NOT NULL, timezone TEXT NOT NULL DEFAULT '',
          format TEXT NOT NULL DEFAULT 'Video', meeting_link TEXT DEFAULT '', meeting_location TEXT DEFAULT '',
          interviewer_names TEXT DEFAULT '', candidate_confirmation TEXT NOT NULL DEFAULT 'Unknown',
          status TEXT NOT NULL DEFAULT 'Scheduled', feedback TEXT DEFAULT '', outcome TEXT DEFAULT '',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS interview_events(
          id INTEGER PRIMARY KEY, interview_id INTEGER NOT NULL, event_type TEXT NOT NULL,
          details TEXT DEFAULT '', created_at TEXT NOT NULL
        );
        """)
init()

@router.post("")
def create_interview(payload:dict):
    submission_id=int(payload.get("submission_id") or 0)
    subs=rows("""SELECT s.*,c.name candidate_name,j.title job_title,cl.company_name
      FROM client_submissions s JOIN candidates c ON c.id=s.candidate_id
      JOIN jobs j ON j.id=s.job_id JOIN clients cl ON cl.id=s.client_id WHERE s.id=?""",(submission_id,))
    if not subs: raise HTTPException(404,"Client submission not found.")
    sub=subs[0]
    if sub["status"] not in ("Manually Submitted","Client Feedback") or sub["feedback_status"]!="Interview Requested":
        raise HTTPException(409,"Client must request an interview on a manually submitted profile before scheduling.")
    if sub["consent_snapshot"]!="Yes": raise HTTPException(409,"Candidate submission consent is missing.")
    scheduled, timezone_name = validate_schedule(payload.get("scheduled_at"),payload.get("timezone"))
    fmt=str(payload.get("format","Video"))
    if fmt not in ("Video","Phone","Onsite"): raise HTTPException(400,"Choose Video, Phone, or Onsite.")
    link=str(payload.get("meeting_link","")).strip()
    if link and not re.match(r"^https?://",link,re.I): raise HTTPException(400,"Meeting link must begin with http:// or https://.")
    round_number=int(payload.get("round_number",1))
    if round_number<1 or round_number>20: raise HTTPException(400,"Interview round must be between 1 and 20.")
    existing=rows("SELECT id FROM interviews WHERE submission_id=? AND round_number=? AND status NOT IN ('Cancelled','No Show')",(submission_id,round_number))
    if existing: raise HTTPException(409,"An active interview already exists for this submission and round. Reschedule that interview or choose another round number.")
    with connect() as c:
        cur=c.execute("""INSERT INTO interviews(submission_id,round_number,round_name,scheduled_at,timezone,format,meeting_link,meeting_location,interviewer_names,candidate_confirmation,status,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,'Unknown','Scheduled',?,?)""",
          (submission_id,round_number,str(payload.get("round_name","Technical")),scheduled,timezone_name,fmt,link,str(payload.get("meeting_location","")),str(payload.get("interviewer_names","")),stamp(),stamp()))
        iid=cur.lastrowid
        c.execute("INSERT INTO interview_events(interview_id,event_type,details,created_at) VALUES(?,?,?,?)",(iid,"Interview scheduled","Round "+str(round_number)+" · "+scheduled+" "+str(payload.get("timezone","")),stamp()))
    return {"id":iid,"status":"Scheduled","message":"Interview schedule recorded. Recru Agent has not sent an invitation."}

@router.get("")
def list_interviews():
    return rows("""SELECT i.*,c.name candidate_name,j.title job_title,cl.company_name
      FROM interviews i JOIN client_submissions s ON s.id=i.submission_id
      JOIN candidates c ON c.id=s.candidate_id JOIN jobs j ON j.id=s.job_id
      JOIN clients cl ON cl.id=s.client_id ORDER BY i.scheduled_at DESC""")

@router.get("/{interview_id}")
def get_interview(interview_id:int):
    data=rows("""SELECT i.*,c.name candidate_name,c.email candidate_email,j.title job_title,cl.company_name
      FROM interviews i JOIN client_submissions s ON s.id=i.submission_id
      JOIN candidates c ON c.id=s.candidate_id JOIN jobs j ON j.id=s.job_id
      JOIN clients cl ON cl.id=s.client_id WHERE i.id=?""",(interview_id,))
    if not data: raise HTTPException(404,"Interview not found.")
    data[0]["events"]=rows("SELECT * FROM interview_events WHERE interview_id=? ORDER BY id DESC",(interview_id,))
    return data[0]

@router.patch("/{interview_id}")
def update_interview(interview_id:int,payload:dict):
    data=rows("SELECT * FROM interviews WHERE id=?",(interview_id,))
    if not data: raise HTTPException(404,"Interview not found.")
    old=data[0]
    if old["status"] in ("Completed","Cancelled","No Show"):
        raise HTTPException(409,"Closed interviews cannot be rescheduled or edited.")
    scheduled, timezone_name = validate_schedule(payload.get("scheduled_at",old["scheduled_at"]),payload.get("timezone",old["timezone"]))
    fmt=payload.get("format",old["format"])
    if fmt not in ("Video","Phone","Onsite"): raise HTTPException(400,"Choose Video, Phone, or Onsite.")
    link=str(payload.get("meeting_link",old["meeting_link"])).strip()
    if link and not re.match(r"^https?://",link,re.I): raise HTTPException(400,"Meeting link must begin with http:// or https://.")
    confirm=payload.get("candidate_confirmation",old["candidate_confirmation"])
    if confirm not in ("Unknown","Confirmed","Declined"): raise HTTPException(400,"Candidate confirmation must be Unknown, Confirmed, or Declined.")
    round_number=int(payload.get("round_number",old["round_number"]))
    if round_number<1 or round_number>20: raise HTTPException(400,"Interview round must be between 1 and 20.")
    duplicate=rows("SELECT id FROM interviews WHERE submission_id=? AND round_number=? AND id<>? AND status NOT IN ('Cancelled','No Show')",(old["submission_id"],round_number,interview_id))
    if duplicate: raise HTTPException(409,"Another active interview already uses this round number for the same submission.")
    schedule_changed = any([
        scheduled != old["scheduled_at"], timezone_name != old["timezone"],
        fmt != old["format"], link != old["meeting_link"],
        str(payload.get("meeting_location",old["meeting_location"])) != old["meeting_location"],
        str(payload.get("interviewer_names",old["interviewer_names"])) != old["interviewer_names"],
        round_number != old["round_number"]
    ])
    new_status = "Cancelled" if confirm=="Declined" else ("Rescheduled" if schedule_changed else old["status"])
    with connect() as c:
        c.execute("""UPDATE interviews SET round_number=?,round_name=?,scheduled_at=?,timezone=?,format=?,meeting_link=?,meeting_location=?,interviewer_names=?,candidate_confirmation=?,status=?,updated_at=? WHERE id=?""",
          (round_number,str(payload.get("round_name",old["round_name"])),scheduled,timezone_name,fmt,link,str(payload.get("meeting_location",old["meeting_location"])),str(payload.get("interviewer_names",old["interviewer_names"])),confirm,new_status,stamp(),interview_id))
        details = "Interview details updated. Status: "+new_status
        c.execute("INSERT INTO interview_events(interview_id,event_type,details,created_at) VALUES(?,?,?,?)",(interview_id,"Interview updated",details,stamp()))
    return {"id":interview_id,"status":new_status,"message":"Interview details updated. Notify the candidate and interviewers manually."}

@router.patch("/{interview_id}/status")
def update_interview_status(interview_id:int,payload:dict):
    data=rows("SELECT status FROM interviews WHERE id=?",(interview_id,))
    if not data: raise HTTPException(404,"Interview not found.")
    status=payload.get("status")
    if status not in ("Scheduled","Rescheduled","Completed","Cancelled","No Show"): raise HTTPException(400,"Invalid interview status.")
    current=rows("SELECT status,candidate_confirmation FROM interviews WHERE id=?",(interview_id,))[0]
    if current["status"] in ("Completed","Cancelled","No Show"):
        raise HTTPException(409,"Closed interviews cannot be reopened. Create a new interview round if needed.")
    if status=="Scheduled" and current["candidate_confirmation"]=="Declined":
        raise HTTPException(409,"The candidate declined this interview. Update the schedule only after confirming a new time with them.")
    with connect() as c:
        c.execute("UPDATE interviews SET status=?,updated_at=? WHERE id=?",(status,stamp(),interview_id))
        c.execute("INSERT INTO interview_events(interview_id,event_type,details,created_at) VALUES(?,?,?,?)",(interview_id,"Status updated",status,stamp()))
    return {"id":interview_id,"status":status}

@router.post("/{interview_id}/feedback")
def interview_feedback(interview_id:int,payload:dict):
    data=rows("SELECT status FROM interviews WHERE id=?",(interview_id,))
    if not data: raise HTTPException(404,"Interview not found.")
    if data[0]["status"] not in ("Completed","Scheduled","Rescheduled"): raise HTTPException(409,"Feedback cannot be recorded for a cancelled or no-show interview.")
    outcome=payload.get("outcome","Pending")
    allowed=("Strong Hire","Hire","No Hire","Maybe","Additional Round","Pending")
    if outcome not in allowed: raise HTTPException(400,"Choose a valid interview outcome.")
    feedback=str(payload.get("feedback",""))
    with connect() as c:
        c.execute("UPDATE interviews SET feedback=?,outcome=?,status='Completed',updated_at=? WHERE id=?",(feedback,outcome,stamp(),interview_id))
        c.execute("INSERT INTO interview_events(interview_id,event_type,details,created_at) VALUES(?,?,?,?)",(interview_id,"Interview feedback recorded",outcome+" · "+feedback,stamp()))
    return {"id":interview_id,"status":"Completed","outcome":outcome}

@router.get("/{interview_id}/history")
def interview_history(interview_id:int):
    if not rows("SELECT id FROM interviews WHERE id=?",(interview_id,)): raise HTTPException(404,"Interview not found.")
    return rows("SELECT * FROM interview_events WHERE interview_id=? ORDER BY id DESC",(interview_id,))
