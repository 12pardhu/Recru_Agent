"""Central recruiter follow-up and reminder tracker."""
import os, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR",str(ROOT/"data")))
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/"recru_agent.db"
router=APIRouter(prefix="/api/followups",tags=["Recruiter Follow-ups"])
TYPES={"Requirement","Candidate","Vendor","Client","Submission","Interview","Offer / Placement","General"}
STATUSES={"Open","In Progress","Completed","Cancelled"}
PRIORITIES={"Low","Normal","High","Urgent"}

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def stamp(): return datetime.now(timezone.utc).isoformat()
def rows(sql,args=()):
    with connect() as c:return [dict(r) for r in c.execute(sql,args).fetchall()]
def valid_date(value):
    try: datetime.fromisoformat(value.replace("Z","+00:00"))
    except (ValueError,AttributeError): raise HTTPException(400,"Follow-up due date/time must be a valid ISO date/time.")

def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS recruiter_followups(
          id INTEGER PRIMARY KEY, title TEXT NOT NULL, followup_type TEXT NOT NULL DEFAULT 'General',
          candidate_id INTEGER, job_id INTEGER, related_party TEXT DEFAULT '',
          due_at TEXT NOT NULL, priority TEXT NOT NULL DEFAULT 'Normal',
          status TEXT NOT NULL DEFAULT 'Open', assigned_to TEXT DEFAULT '',
          notes TEXT DEFAULT '', completed_at TEXT DEFAULT '',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_recruiter_followups_due ON recruiter_followups(status,due_at);
        """)
init()

class FollowupCreate(BaseModel):
    title:str=Field(min_length=2,max_length=240)
    followup_type:str="General"
    candidate_id:int|None=None
    job_id:int|None=None
    related_party:str=Field(default="",max_length=240)
    due_at:str
    priority:str="Normal"
    assigned_to:str=Field(default="",max_length=160)
    notes:str=Field(default="",max_length=4000)

class FollowupUpdate(BaseModel):
    title:str|None=Field(default=None,min_length=2,max_length=240)
    followup_type:str|None=None
    candidate_id:int|None=None
    job_id:int|None=None
    related_party:str|None=Field(default=None,max_length=240)
    due_at:str|None=None
    priority:str|None=None
    status:str|None=None
    assigned_to:str|None=Field(default=None,max_length=160)
    notes:str|None=Field(default=None,max_length=4000)

@router.get("")
def list_followups(status:str|None=None,due_only:bool=False,overdue_only:bool=False):
    sql="""SELECT f.*,c.name candidate_name,j.title job_title
      FROM recruiter_followups f LEFT JOIN candidates c ON c.id=f.candidate_id
      LEFT JOIN jobs j ON j.id=f.job_id WHERE 1=1"""
    args=[]
    if status:
        if status not in STATUSES:raise HTTPException(400,"Invalid follow-up status.")
        sql+=" AND f.status=?";args.append(status)
    if due_only:
        sql+=" AND f.status IN ('Open','In Progress') AND f.due_at<=?";args.append(stamp())
    if overdue_only:
        sql+=" AND f.status IN ('Open','In Progress') AND f.due_at<?";args.append(stamp())
    sql+=" ORDER BY CASE WHEN f.status IN ('Open','In Progress') THEN 0 ELSE 1 END, f.due_at ASC, f.id DESC"
    return rows(sql,tuple(args))

@router.post("")
def create_followup(payload:FollowupCreate):
    if payload.followup_type not in TYPES:raise HTTPException(400,"Choose a supported follow-up type.")
    if payload.priority not in PRIORITIES:raise HTTPException(400,"Choose a supported priority.")
    valid_date(payload.due_at)
    if payload.candidate_id is not None and not rows("SELECT id FROM candidates WHERE id=?",(payload.candidate_id,)):
        raise HTTPException(404,"Candidate not found.")
    if payload.job_id is not None and not rows("SELECT id FROM jobs WHERE id=?",(payload.job_id,)):
        raise HTTPException(404,"Job requirement not found.")
    ts=stamp()
    with connect() as c:
        cur=c.execute("""INSERT INTO recruiter_followups(title,followup_type,candidate_id,job_id,related_party,due_at,priority,assigned_to,notes,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(payload.title.strip(),payload.followup_type,payload.candidate_id,payload.job_id,payload.related_party.strip(),payload.due_at,payload.priority,payload.assigned_to.strip(),payload.notes.strip(),ts,ts))
        return {"id":cur.lastrowid,"message":"Follow-up reminder created."}

@router.patch("/{followup_id}")
def update_followup(followup_id:int,payload:FollowupUpdate):
    current=rows("SELECT * FROM recruiter_followups WHERE id=?",(followup_id,))
    if not current:raise HTTPException(404,"Follow-up reminder not found.")
    old=current[0]
    values={}
    for key in ("title","followup_type","candidate_id","job_id","related_party","due_at","priority","status","assigned_to","notes"):
        value=getattr(payload,key)
        values[key]=value if value is not None else old[key]
    if values["followup_type"] not in TYPES:raise HTTPException(400,"Choose a supported follow-up type.")
    if values["priority"] not in PRIORITIES:raise HTTPException(400,"Choose a supported priority.")
    if values["status"] not in STATUSES:raise HTTPException(400,"Choose a supported follow-up status.")
    valid_date(values["due_at"])
    if values["candidate_id"] is not None and not rows("SELECT id FROM candidates WHERE id=?",(values["candidate_id"],)):
        raise HTTPException(404,"Candidate not found.")
    if values["job_id"] is not None and not rows("SELECT id FROM jobs WHERE id=?",(values["job_id"],)):
        raise HTTPException(404,"Job requirement not found.")
    completed=stamp() if values["status"]=="Completed" else ""
    with connect() as c:
        c.execute("""UPDATE recruiter_followups SET title=?,followup_type=?,candidate_id=?,job_id=?,related_party=?,due_at=?,priority=?,status=?,assigned_to=?,notes=?,completed_at=?,updated_at=? WHERE id=?""",
          (values["title"],values["followup_type"],values["candidate_id"],values["job_id"],values["related_party"],values["due_at"],values["priority"],values["status"],values["assigned_to"],values["notes"],completed,stamp(),followup_id))
    return {"id":followup_id,"status":values["status"],"message":"Follow-up reminder updated."}
