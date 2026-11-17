import os, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR",str(ROOT/"data")))
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/"recru_agent.db"
router=APIRouter(prefix="/api/pipeline",tags=["Recruitment Pipeline"])
STAGES=("Sourcing","Qualification","Screening","Client Submission","Interview","Offer","Placed","Rejected","Withdrawn")
STATUSES=("Active","Waiting","Completed")

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def stamp():
    return datetime.now(timezone.utc).isoformat()

def rows(sql,args=()):
    with connect() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]

def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS recruitment_pipeline(
          id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL, job_id INTEGER NOT NULL,
          current_stage TEXT NOT NULL DEFAULT 'Sourcing', stage_status TEXT NOT NULL DEFAULT 'Active',
          owner TEXT DEFAULT '', next_action TEXT DEFAULT '', due_at TEXT DEFAULT '',
          notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(candidate_id,job_id)
        );
        CREATE TABLE IF NOT EXISTS pipeline_events(
          id INTEGER PRIMARY KEY, pipeline_id INTEGER NOT NULL, event_type TEXT NOT NULL,
          details TEXT DEFAULT '', created_at TEXT NOT NULL
        );
        """)
init()

def ensure_pipeline(candidate_id,job_id,stage="Sourcing"):
    if stage not in STAGES: raise HTTPException(400,"Invalid recruitment pipeline stage.")
    existing=rows("SELECT id,current_stage FROM recruitment_pipeline WHERE candidate_id=? AND job_id=?",(candidate_id,job_id))
    if existing: return existing[0]["id"]
    initial_status = "Completed" if stage in ("Placed","Rejected","Withdrawn") else "Active"
    with connect() as c:
        cur=c.execute("INSERT INTO recruitment_pipeline(candidate_id,job_id,current_stage,stage_status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
          (candidate_id,job_id,stage,initial_status,stamp(),stamp()))
        pid=cur.lastrowid
        c.execute("INSERT INTO pipeline_events(pipeline_id,event_type,details,created_at) VALUES(?,?,?,?)",(pid,"Pipeline created","Initial stage: "+stage,stamp()))
    return pid

def advance_pipeline(candidate_id,job_id,stage,details=""):
    if stage not in STAGES: return None
    pid=ensure_pipeline(candidate_id,job_id,stage)
    current=rows("SELECT current_stage FROM recruitment_pipeline WHERE id=?",(pid,))[0]["current_stage"]
    terminal=("Placed","Rejected","Withdrawn")
    if current in terminal: return pid
    order={s:i for i,s in enumerate(STAGES[:6])}
    if stage in order and current in order and order[stage]<order[current]: return pid
    next_status = "Completed" if stage in terminal else "Active"
    with connect() as c:
        c.execute("UPDATE recruitment_pipeline SET current_stage=?,stage_status=?,updated_at=? WHERE id=?",(stage,next_status,stamp(),pid))
        c.execute("INSERT INTO pipeline_events(pipeline_id,event_type,details,created_at) VALUES(?,?,?,?)",(pid,"Stage advanced",stage+((" · "+details) if details else ""),stamp()))
    return pid

@router.post("/ensure")
def create_pipeline_item(payload:dict):
    try:
        candidate_id=int(payload.get("candidate_id") or 0); job_id=int(payload.get("job_id") or 0)
    except (TypeError,ValueError):
        raise HTTPException(400,"Choose a valid candidate and job requirement.")
    if not rows("SELECT id FROM candidates WHERE id=?",(candidate_id,)): raise HTTPException(404,"Candidate not found.")
    if not rows("SELECT id FROM jobs WHERE id=?",(job_id,)): raise HTTPException(404,"Job not found.")
    if not rows("SELECT id FROM job_versions WHERE job_id=? LIMIT 1",(job_id,)):
        raise HTTPException(409,"Confirm the job requirement before adding it to the recruitment pipeline.")
    stage=str(payload.get("stage","Sourcing"))
    if stage not in STAGES: raise HTTPException(400,"Invalid recruitment pipeline stage.")
    pid=ensure_pipeline(candidate_id,job_id,stage)
    return {"id":pid,"message":"Pipeline record available."}

@router.get("")
def list_pipeline():
    return rows("""SELECT p.*,c.name candidate_name,c.location candidate_location,j.title job_title
      FROM recruitment_pipeline p JOIN candidates c ON c.id=p.candidate_id
      JOIN jobs j ON j.id=p.job_id ORDER BY p.updated_at DESC""")

@router.get("/{pipeline_id}")
def get_pipeline(pipeline_id:int):
    data=rows("""SELECT p.*,c.name candidate_name,j.title job_title
      FROM recruitment_pipeline p JOIN candidates c ON c.id=p.candidate_id
      JOIN jobs j ON j.id=p.job_id WHERE p.id=?""",(pipeline_id,))
    if not data: raise HTTPException(404,"Pipeline record not found.")
    data[0]["events"]=rows("SELECT * FROM pipeline_events WHERE pipeline_id=? ORDER BY id DESC",(pipeline_id,))
    return data[0]

@router.patch("/{pipeline_id}")
def update_pipeline(pipeline_id:int,payload:dict):
    data=rows("SELECT * FROM recruitment_pipeline WHERE id=?",(pipeline_id,))
    if not data: raise HTTPException(404,"Pipeline record not found.")
    stage=payload.get("current_stage",data[0]["current_stage"])
    status=payload.get("stage_status",data[0]["stage_status"])
    if stage not in STAGES: raise HTTPException(400,"Invalid recruitment pipeline stage.")
    if status not in STATUSES: raise HTTPException(400,"Invalid pipeline stage status.")
    old=data[0]
    terminal=("Placed","Rejected","Withdrawn")
    if old["current_stage"] in terminal and stage != old["current_stage"]:
        raise HTTPException(409,"Placed, Rejected, and Withdrawn are closed pipeline outcomes. Create a new job/candidate pipeline record if a new process is required.")
    order={s:i for i,s in enumerate(STAGES[:6])}
    if stage in order and old["current_stage"] in order and order[stage]<order[old["current_stage"]]:
        raise HTTPException(409,"Pipeline stages cannot move backwards. Add a recruiter activity note if a previous step needs revisiting.")
    if stage in terminal: status="Completed"
    due_at=str(payload.get("due_at",old["due_at"])).strip()
    if due_at:
        try: datetime.fromisoformat(due_at.replace("Z","+00:00"))
        except ValueError: raise HTTPException(400,"Enter a valid next-action due date/time in ISO format.")
    next_action=str(payload.get("next_action",old["next_action"])).strip()
    if status=="Active" and not next_action:
        raise HTTPException(400,"Add a next action when the pipeline record is Active.")
    stage_changed = stage != old["current_stage"]
    with connect() as c:
        c.execute("UPDATE recruitment_pipeline SET current_stage=?,stage_status=?,owner=?,next_action=?,due_at=?,notes=?,updated_at=? WHERE id=?",
          (stage,status,str(payload.get("owner",old["owner"])),next_action,due_at,str(payload.get("notes",old["notes"])),stamp(),pipeline_id))
        details=("Stage changed: "+old["current_stage"]+" → "+stage+"; " if stage_changed else "")+"Status: "+status+"; next action: "+next_action
        c.execute("INSERT INTO pipeline_events(pipeline_id,event_type,details,created_at) VALUES(?,?,?,?)",(pipeline_id,"Pipeline updated",details,stamp()))
    return {"id":pipeline_id,"current_stage":stage,"stage_status":status,"message":"Pipeline record updated."}

@router.post("/{pipeline_id}/activity")
def add_pipeline_activity(pipeline_id:int,payload:dict):
    if not rows("SELECT id FROM recruitment_pipeline WHERE id=?",(pipeline_id,)): raise HTTPException(404,"Pipeline record not found.")
    details=str(payload.get("details","")).strip()
    if not details: raise HTTPException(400,"Activity details are required.")
    with connect() as c:
        c.execute("INSERT INTO pipeline_events(pipeline_id,event_type,details,created_at) VALUES(?,?,?,?)",(pipeline_id,str(payload.get("event_type","Recruiter note")),details,stamp()))
        c.execute("UPDATE recruitment_pipeline SET updated_at=? WHERE id=?",(stamp(),pipeline_id))
    return {"id":pipeline_id,"message":"Pipeline activity recorded."}

@router.get("/{pipeline_id}/history")
def pipeline_history(pipeline_id:int):
    if not rows("SELECT id FROM recruitment_pipeline WHERE id=?",(pipeline_id,)): raise HTTPException(404,"Pipeline record not found.")
    return rows("SELECT * FROM pipeline_events WHERE pipeline_id=? ORDER BY id DESC",(pipeline_id,))
