"""Offer, placement, onboarding and post-joining follow-up tracking."""
import json, os, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR",str(ROOT/"data")))
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/"recru_agent.db"
router=APIRouter(prefix="/api/offers",tags=["Offer and Placement Management"])

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def stamp(): return datetime.now(timezone.utc).isoformat()

def rows(sql,args=()):
    with connect() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]

def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS candidate_offers(
          id INTEGER PRIMARY KEY, submission_id INTEGER NOT NULL UNIQUE,
          candidate_id INTEGER NOT NULL, job_id INTEGER NOT NULL, client_id INTEGER NOT NULL,
          offer_type TEXT DEFAULT 'Contract', offered_rate TEXT DEFAULT '', currency TEXT DEFAULT 'USD',
          pay_frequency TEXT DEFAULT 'Hourly', work_arrangement TEXT DEFAULT '',
          offer_status TEXT NOT NULL DEFAULT 'Received', offer_date TEXT DEFAULT '',
          response_due TEXT DEFAULT '', accepted_at TEXT DEFAULT '', declined_at TEXT DEFAULT '',
          planned_start_date TEXT DEFAULT '', joining_status TEXT NOT NULL DEFAULT 'Not Started',
          joined_at TEXT DEFAULT '', onboarding_checklist TEXT NOT NULL DEFAULT '{}',
          follow_up_at TEXT DEFAULT '', follow_up_notes TEXT DEFAULT '', recruiter_notes TEXT DEFAULT '',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS offer_events(
          id INTEGER PRIMARY KEY, offer_id INTEGER NOT NULL, event_type TEXT NOT NULL,
          details TEXT DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_offer_followup ON candidate_offers(follow_up_at);
        """)
init()

class OfferCreate(BaseModel):
    submission_id:int
    offer_type:str="Contract"
    offered_rate:str=""
    currency:str="USD"
    pay_frequency:str="Hourly"
    work_arrangement:str=""
    offer_date:str=""
    response_due:str=""
    planned_start_date:str=""
    recruiter_notes:str=""

class OfferUpdate(BaseModel):
    offer_status:str|None=None
    offered_rate:str|None=None
    currency:str|None=None
    pay_frequency:str|None=None
    work_arrangement:str|None=None
    offer_date:str|None=None
    response_due:str|None=None
    planned_start_date:str|None=None
    joining_status:str|None=None
    joined_at:str|None=None
    onboarding_checklist:dict|None=None
    follow_up_at:str|None=None
    follow_up_notes:str|None=None
    recruiter_notes:str|None=None
    event_details:str=""

def valid_date(value,label):
    if not value:return
    try: datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError: raise HTTPException(400,label+" must be a valid ISO date/time.")

@router.get("")
def list_offers():
    return rows("""SELECT o.*,c.name candidate_name,j.title job_title,cl.company_name
      FROM candidate_offers o JOIN candidates c ON c.id=o.candidate_id
      JOIN jobs j ON j.id=o.job_id JOIN clients cl ON cl.id=o.client_id
      ORDER BY o.updated_at DESC""")

@router.post("")
def create_offer(payload:OfferCreate):
    subs=rows("""SELECT s.*,c.company_name FROM client_submissions s
      JOIN clients c ON c.id=s.client_id WHERE s.id=?""",(payload.submission_id,))
    if not subs: raise HTTPException(404,"Client submission not found.")
    sub=subs[0]
    if sub["status"] not in ("Manually Submitted","Client Feedback") or sub.get("feedback_status")!="Offer":
        raise HTTPException(409,"Record an Offer client-feedback outcome after manual submission before creating an offer.")
    if rows("SELECT id FROM candidate_offers WHERE submission_id=?",(payload.submission_id,)):
        raise HTTPException(409,"An offer record already exists for this client submission.")
    for v,l in ((payload.offer_date,"Offer date"),(payload.response_due,"Response due"),(payload.planned_start_date,"Planned start date")):valid_date(v,l)
    if payload.offer_type not in ("Contract","Full-time","Part-time","C2C","W2","1099","Other"):
        raise HTTPException(400,"Choose a supported offer type.")
    with connect() as c:
        cur=c.execute("""INSERT INTO candidate_offers
          (submission_id,candidate_id,job_id,client_id,offer_type,offered_rate,currency,pay_frequency,work_arrangement,offer_date,response_due,planned_start_date,recruiter_notes,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (payload.submission_id,sub["candidate_id"],sub["job_id"],sub["client_id"],payload.offer_type,
           payload.offered_rate,payload.currency,payload.pay_frequency,payload.work_arrangement,
           payload.offer_date,payload.response_due,payload.planned_start_date,payload.recruiter_notes,stamp(),stamp()))
        oid=cur.lastrowid
        c.execute("INSERT INTO offer_events(offer_id,event_type,details,created_at) VALUES(?,?,?,?)",
          (oid,"Offer recorded","Offer details recorded from client feedback. No acceptance or candidate notification was automated.",stamp()))
        c.execute("UPDATE recruitment_pipeline SET current_stage='Offer',stage_status='Active',updated_at=? WHERE candidate_id=? AND job_id=?",
          (stamp(),sub["candidate_id"],sub["job_id"]))
    return {"id":oid,"message":"Offer record created. Recruiter must confirm the candidate's response."}

@router.get("/{offer_id}")
def get_offer(offer_id:int):
    data=rows("""SELECT o.*,c.name candidate_name,j.title job_title,cl.company_name
      FROM candidate_offers o JOIN candidates c ON c.id=o.candidate_id
      JOIN jobs j ON j.id=o.job_id JOIN clients cl ON cl.id=o.client_id WHERE o.id=?""",(offer_id,))
    if not data:raise HTTPException(404,"Offer record not found.")
    try:data[0]["onboarding_checklist"]=json.loads(data[0]["onboarding_checklist"] or "{}")
    except Exception:data[0]["onboarding_checklist"]={}
    data[0]["events"]=rows("SELECT * FROM offer_events WHERE offer_id=? ORDER BY id DESC",(offer_id,))
    return data[0]

@router.patch("/{offer_id}")
def update_offer(offer_id:int,payload:OfferUpdate):
    old=rows("SELECT * FROM candidate_offers WHERE id=?",(offer_id,))
    if not old:raise HTTPException(404,"Offer record not found.")
    o=old[0]
    statuses={"Received","Presented to Candidate","Accepted","Declined","Withdrawn","Expired"}
    joining={"Not Started","Preparing","Ready","Joined","Did Not Join"}
    status=payload.offer_status if payload.offer_status is not None else o["offer_status"]
    join=payload.joining_status if payload.joining_status is not None else o["joining_status"]
    if status not in statuses:raise HTTPException(400,"Invalid offer status.")
    if join not in joining:raise HTTPException(400,"Invalid joining status.")
    if join=="Joined" and status!="Accepted":raise HTTPException(409,"Confirm candidate acceptance before recording joining.")
    for v,l in ((payload.offer_date,"Offer date"),(payload.response_due,"Response due"),(payload.planned_start_date,"Planned start date"),(payload.joined_at,"Joined date"),(payload.follow_up_at,"Follow-up date")):
        if v is not None:valid_date(v,l)
    checklist=payload.onboarding_checklist if payload.onboarding_checklist is not None else json.loads(o["onboarding_checklist"] or "{}")
    if not isinstance(checklist,dict):raise HTTPException(400,"Onboarding checklist must be an object of task names and completion values.")
    for k,v in checklist.items():
        if not isinstance(k,str) or not isinstance(v,bool):raise HTTPException(400,"Onboarding checklist values must be true/false.")
    if join=="Joined":
        incomplete=[k for k,v in checklist.items() if not v]
        if incomplete:raise HTTPException(409,"Complete all listed onboarding checklist items before recording Joined: "+", ".join(incomplete))
    with connect() as c:
        c.execute("""UPDATE candidate_offers SET offer_status=?,offered_rate=?,currency=?,pay_frequency=?,work_arrangement=?,
          offer_date=?,response_due=?,planned_start_date=?,joining_status=?,joined_at=?,onboarding_checklist=?,
          follow_up_at=?,follow_up_notes=?,recruiter_notes=?,updated_at=? WHERE id=?""",
          (status,payload.offered_rate if payload.offered_rate is not None else o["offered_rate"],
           payload.currency if payload.currency is not None else o["currency"],
           payload.pay_frequency if payload.pay_frequency is not None else o["pay_frequency"],
           payload.work_arrangement if payload.work_arrangement is not None else o["work_arrangement"],
           payload.offer_date if payload.offer_date is not None else o["offer_date"],
           payload.response_due if payload.response_due is not None else o["response_due"],
           payload.planned_start_date if payload.planned_start_date is not None else o["planned_start_date"],
           join,payload.joined_at if payload.joined_at is not None else o["joined_at"],
           json.dumps(checklist),payload.follow_up_at if payload.follow_up_at is not None else o["follow_up_at"],
           payload.follow_up_notes if payload.follow_up_notes is not None else o["follow_up_notes"],
           payload.recruiter_notes if payload.recruiter_notes is not None else o["recruiter_notes"],stamp(),offer_id))
        details=payload.event_details.strip() or ("Offer status: "+status+"; joining: "+join)
        c.execute("INSERT INTO offer_events(offer_id,event_type,details,created_at) VALUES(?,?,?,?)",(offer_id,"Offer / placement update",details,stamp()))
        if status=="Accepted":
            c.execute("UPDATE recruitment_pipeline SET current_stage='Offer',stage_status='Active',next_action='Confirm start date and onboarding',updated_at=? WHERE candidate_id=? AND job_id=?",(stamp(),o["candidate_id"],o["job_id"]))
        if join=="Joined":
            c.execute("UPDATE recruitment_pipeline SET current_stage='Placed',stage_status='Completed',next_action='Post-placement follow-up',updated_at=? WHERE candidate_id=? AND job_id=?",(stamp(),o["candidate_id"],o["job_id"]))
    return {"id":offer_id,"offer_status":status,"joining_status":join,"message":"Offer and placement record updated."}

@router.get("/{offer_id}/history")
def offer_history(offer_id:int):
    if not rows("SELECT id FROM candidate_offers WHERE id=?",(offer_id,)):raise HTTPException(404,"Offer record not found.")
    return rows("SELECT * FROM offer_events WHERE offer_id=? ORDER BY id DESC",(offer_id,))
