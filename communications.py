import os, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR",str(ROOT/"data")))
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/"recru_agent.db"
router=APIRouter(prefix="/api/communications",tags=["Candidate Communication"])

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def stamp():
    return datetime.now(timezone.utc).isoformat()

def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS communication_templates(
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, channel TEXT NOT NULL,
          subject_template TEXT DEFAULT '', body_template TEXT NOT NULL, active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS communication_messages(
          id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL, job_id INTEGER,
          template_id INTEGER, channel TEXT NOT NULL, subject TEXT DEFAULT '',
          body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Draft',
          approval_notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          approved_at TEXT DEFAULT '', manually_sent_at TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS communication_events(
          id INTEGER PRIMARY KEY, message_id INTEGER NOT NULL, event_type TEXT NOT NULL,
          details TEXT DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS candidate_contact_interactions(
          id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL, job_id INTEGER,
          channel TEXT NOT NULL, direction TEXT NOT NULL DEFAULT 'Outbound',
          outcome TEXT NOT NULL DEFAULT 'Attempted', notes TEXT DEFAULT '',
          follow_up_at TEXT DEFAULT '', created_at TEXT NOT NULL, created_by TEXT DEFAULT 'Recruiter'
        );
        CREATE INDEX IF NOT EXISTS idx_contact_interactions_candidate ON candidate_contact_interactions(candidate_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_contact_interactions_followup ON candidate_contact_interactions(follow_up_at);
        """)
        defaults=[
          ("Initial opportunity outreach","Email","Opportunity to discuss {job_title}","Hi {candidate_name},\n\nI am reaching out about a {job_title} opportunity{location_phrase}. Your background in {skills} may be relevant to the role. Would you be open to a brief conversation to learn more?\n\nIf interested, please let me know a convenient time.\n\nRegards,\nRecruiter"),
          ("LinkedIn introduction","LinkedIn","","Hi {candidate_name}, I am reaching out about a {job_title} opportunity{location_phrase}. Your experience with {skills} may be relevant. Would you be open to connecting and hearing more?"),
          ("Follow-up","Email","Following up — {job_title}","Hi {candidate_name},\n\nI wanted to follow up on my earlier note about the {job_title} opportunity. If you are interested, I would be happy to share the details. If it is not a fit, no worries.\n\nRegards,\nRecruiter"),
          ("Screening availability request","Email","Availability for a {job_title} discussion","Hi {candidate_name},\n\nWould you be available for a short discussion about the {job_title} opportunity? Please share a few time windows that work for you.\n\nRegards,\nRecruiter"),
          ("Work authorization and engagement check","Email","A few questions about the {job_title} role","Hi {candidate_name},\n\nBefore we proceed with the {job_title} opportunity, could you please confirm your current work authorization and whether W2, C2C, or another engagement type is acceptable to you? Please share only the information you are comfortable providing.\n\nRegards,\nRecruiter")
        ]
        for name,channel,subject,body in defaults:
            exists=c.execute("SELECT id FROM communication_templates WHERE name=?",(name,)).fetchone()
            if not exists:
                c.execute("INSERT INTO communication_templates(name,channel,subject_template,body_template) VALUES(?,?,?,?)",(name,channel,subject,body))
init()

class MessageEdit(BaseModel):
    subject: str = ""
    body: str

class ContactInteraction(BaseModel):
    candidate_id: int
    job_id: int | None = None
    channel: str
    direction: str = "Outbound"
    outcome: str = "Attempted"
    notes: str = ""
    follow_up_at: str = ""
    created_by: str = "Recruiter"

def rows(sql,args=()):
    with connect() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]

def render(template,value):
    candidate=value["candidate"]; job=value.get("job") or {}
    location=(job.get("location") or "").strip()
    phrase=(" in "+location) if location else ""
    data={"candidate_name":candidate.get("name") or "there",
      "job_title":job.get("title") or "an opportunity",
      "location_phrase":phrase,
      "skills":candidate.get("skills") or "your technical background"}
    subject=template["subject_template"] or ""
    body=template["body_template"] or ""
    for key,val in data.items():
        subject=subject.replace("{"+key+"}",val)
        body=body.replace("{"+key+"}",val)
    return subject,body


@router.get("/interactions")
def list_interactions(candidate_id: int | None = None, job_id: int | None = None, due_only: bool = False):
    sql = """SELECT i.*, c.name candidate_name, j.title job_title
             FROM candidate_contact_interactions i
             JOIN candidates c ON c.id=i.candidate_id
             LEFT JOIN jobs j ON j.id=i.job_id WHERE 1=1"""
    args = []
    if candidate_id is not None:
        sql += " AND i.candidate_id=?"; args.append(candidate_id)
    if job_id is not None:
        sql += " AND i.job_id=?"; args.append(job_id)
    if due_only:
        sql += " AND i.follow_up_at<>'' AND i.follow_up_at<=?"
        args.append(stamp())
    sql += " ORDER BY CASE WHEN i.follow_up_at='' THEN 1 ELSE 0 END, i.follow_up_at, i.id DESC"
    return rows(sql, tuple(args))


@router.post("/interactions")
def create_interaction(payload: ContactInteraction):
    allowed_channels = {"LinkedIn", "Phone", "Email", "WhatsApp"}
    allowed_directions = {"Outbound", "Inbound"}
    allowed_outcomes = {"Attempted", "Connected", "No Answer", "Voicemail", "Replied", "Interested", "Not Interested", "Follow-up Needed", "Do Not Contact"}
    if payload.channel not in allowed_channels:
        raise HTTPException(400, "Channel must be LinkedIn, Phone, Email, or WhatsApp.")
    if payload.direction not in allowed_directions:
        raise HTTPException(400, "Direction must be Inbound or Outbound.")
    if payload.outcome not in allowed_outcomes:
        raise HTTPException(400, "Choose a supported contact outcome.")
    if not rows("SELECT id FROM candidates WHERE id=?", (payload.candidate_id,)):
        raise HTTPException(404, "Candidate not found.")
    if payload.job_id is not None and not rows("SELECT id FROM jobs WHERE id=?", (payload.job_id,)):
        raise HTTPException(404, "Job requirement not found.")
    candidate = rows("SELECT do_not_contact,contact_preference FROM candidates WHERE id=?", (payload.candidate_id,))[0]
    if payload.direction == "Outbound" and (candidate.get("do_not_contact") or candidate.get("contact_preference") == "Do not contact"):
        raise HTTPException(409, "Candidate is marked Do not contact; outbound contact cannot be logged.")
    if payload.follow_up_at:
        try:
            datetime.fromisoformat(payload.follow_up_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "Follow-up must be a valid ISO date/time.")
    with connect() as c:
        cur = c.execute("""INSERT INTO candidate_contact_interactions
          (candidate_id,job_id,channel,direction,outcome,notes,follow_up_at,created_at,created_by)
          VALUES(?,?,?,?,?,?,?,?,?)""",
          (payload.candidate_id,payload.job_id,payload.channel,payload.direction,payload.outcome,
           payload.notes.strip(),payload.follow_up_at,stamp(),payload.created_by.strip() or "Recruiter"))
        interaction_id = cur.lastrowid
        if payload.outcome == "Do Not Contact":
            c.execute("UPDATE candidates SET do_not_contact=1, contact_preference='Do not contact' WHERE id=?", (payload.candidate_id,))
    return {"id": interaction_id, "message": "Contact activity recorded. No message or call was initiated by Recru Agent."}


@router.get("/interactions/{interaction_id}")
def get_interaction(interaction_id: int):
    data = rows("""SELECT i.*,c.name candidate_name,j.title job_title
                   FROM candidate_contact_interactions i
                   JOIN candidates c ON c.id=i.candidate_id
                   LEFT JOIN jobs j ON j.id=i.job_id WHERE i.id=?""", (interaction_id,))
    if not data:
        raise HTTPException(404, "Contact activity not found.")
    return data[0]

@router.get("/templates")
def list_templates():
    return rows("SELECT * FROM communication_templates WHERE active=1 ORDER BY id")

@router.post("/drafts")
def create_message(payload:dict):
    candidate_id=int(payload.get("candidate_id") or 0)
    template_id=int(payload.get("template_id") or 0)
    channel=str(payload.get("channel") or "")
    candidates=rows("SELECT * FROM candidates WHERE id=?",(candidate_id,))
    if not candidates: raise HTTPException(404,"Candidate not found.")
    candidate=candidates[0]
    if candidate.get("do_not_contact") or candidate.get("contact_preference")=="Do not contact":
        raise HTTPException(409,"This candidate is marked Do not contact. No message draft can be created.")
    if channel not in ("Email","LinkedIn"):
        raise HTTPException(400,"Choose Email or LinkedIn as the channel.")
    if candidate.get("contact_preference") in ("Email","LinkedIn","Phone") and candidate["contact_preference"]!=channel:
        raise HTTPException(409,"The selected channel differs from the candidate's recorded contact preference.")
    if channel=="Email" and not candidate.get("email"):
        raise HTTPException(400,"This candidate has no email address recorded.")
    if channel=="LinkedIn" and not candidate.get("linkedin_url"):
        raise HTTPException(400,"This candidate has no LinkedIn profile URL recorded.")
    templates=rows("SELECT * FROM communication_templates WHERE id=? AND active=1",(template_id,))
    if not templates: raise HTTPException(404,"Communication template not found.")
    template=templates[0]
    if template["channel"] not in ("Any",channel):
        raise HTTPException(400,"This template is not designed for the selected channel.")
    job_id=payload.get("job_id")
    job=None
    if job_id:
        jobs=rows("SELECT * FROM jobs WHERE id=?",(int(job_id),))
        if not jobs: raise HTTPException(404,"Job requirement not found.")
        if not rows("SELECT id FROM job_versions WHERE job_id=? LIMIT 1",(int(job_id),)): raise HTTPException(409,"Confirm the job requirement before creating candidate communication.")
        job=jobs[0]
    subject,body=render(template,{"candidate":candidate,"job":job})
    with connect() as c:
        cur=c.execute("INSERT INTO communication_messages(candidate_id,job_id,template_id,channel,subject,body,status,created_at,updated_at) VALUES(?,?,?,?,?,?,'Draft',?,?)",
          (candidate_id,int(job_id) if job_id else None,template_id,channel,subject,body,stamp(),stamp()))
        message_id=cur.lastrowid
        c.execute("INSERT INTO communication_events(message_id,event_type,details,created_at) VALUES(?,?,?,?)",(message_id,"Draft created","Template: "+template["name"],stamp()))
    return {"id":message_id,"status":"Draft","subject":subject,"body":body,"message":"Draft created. Nothing has been sent."}

@router.get("/messages")
def list_messages():
    return rows("""SELECT m.*,c.name candidate_name,c.email candidate_email,c.linkedin_url,j.title job_title
      FROM communication_messages m JOIN candidates c ON c.id=m.candidate_id
      LEFT JOIN jobs j ON j.id=m.job_id ORDER BY m.id DESC""")

@router.get("/messages/{message_id}")
def get_message(message_id:int):
    data=rows("""SELECT m.*,c.name candidate_name,c.email candidate_email,c.linkedin_url,j.title job_title
      FROM communication_messages m JOIN candidates c ON c.id=m.candidate_id
      LEFT JOIN jobs j ON j.id=m.job_id WHERE m.id=?""",(message_id,))
    if not data: raise HTTPException(404,"Message draft not found.")
    data[0]["events"]=rows("SELECT * FROM communication_events WHERE message_id=? ORDER BY id DESC",(message_id,))
    return data[0]

@router.patch("/messages/{message_id}")
def edit_message(message_id:int,payload:MessageEdit):
    messages=rows("SELECT * FROM communication_messages WHERE id=?",(message_id,))
    if not messages: raise HTTPException(404,"Message draft not found.")
    if messages[0]["status"] not in ("Draft","Pending Approval"):
        raise HTTPException(409,"Only draft or pending-approval messages can be edited.")
    with connect() as c:
        c.execute("UPDATE communication_messages SET subject=?,body=?,status='Draft',updated_at=? WHERE id=?",
          (payload.subject,payload.body,stamp(),message_id))
        c.execute("INSERT INTO communication_events(message_id,event_type,details,created_at) VALUES(?,?,?,?)",(message_id,"Draft edited","Message content updated; approval reset.",stamp()))
    return {"id":message_id,"status":"Draft","message":"Changes saved. Approval must be requested again."}

@router.post("/messages/{message_id}/submit-for-approval")
def submit_for_approval(message_id:int):
    messages=rows("SELECT m.*,c.do_not_contact,c.contact_preference FROM communication_messages m JOIN candidates c ON c.id=m.candidate_id WHERE m.id=?",(message_id,))
    if not messages: raise HTTPException(404,"Message draft not found.")
    m=messages[0]
    if m["do_not_contact"] or m["contact_preference"]=="Do not contact": raise HTTPException(409,"Candidate is marked Do not contact.")
    if m["contact_preference"] in ("Email","LinkedIn","Phone") and m["contact_preference"]!=m["channel"]: raise HTTPException(409,"Candidate contact preference no longer matches this message channel.")
    if m["status"] not in ("Draft",): raise HTTPException(409,"Only a draft can be submitted for approval.")
    if not m["body"].strip(): raise HTTPException(400,"Message body cannot be empty.")
    with connect() as c:
        c.execute("UPDATE communication_messages SET status='Pending Approval',updated_at=? WHERE id=?",(stamp(),message_id))
        c.execute("INSERT INTO communication_events(message_id,event_type,details,created_at) VALUES(?,?,?,?)",(message_id,"Submitted for approval","Awaiting human approval.",stamp()))
    return {"id":message_id,"status":"Pending Approval","message":"Sent to the human approval queue. Nothing has been sent."}

@router.post("/messages/{message_id}/approve")
def approve_message(message_id:int,payload:dict):
    messages=rows("SELECT m.*,c.do_not_contact,c.contact_preference FROM communication_messages m JOIN candidates c ON c.id=m.candidate_id WHERE m.id=?",(message_id,))
    if not messages: raise HTTPException(404,"Message draft not found.")
    m=messages[0]
    if m["do_not_contact"] or m["contact_preference"]=="Do not contact": raise HTTPException(409,"Candidate is marked Do not contact.")
    if m["contact_preference"] in ("Email","LinkedIn","Phone") and m["contact_preference"]!=m["channel"]: raise HTTPException(409,"Candidate contact preference no longer matches this message channel.")
    if m["status"]!="Pending Approval": raise HTTPException(409,"Only pending messages can be approved.")
    approver=str(payload.get("approver","Recruiter")).strip() or "Recruiter"
    with connect() as c:
        c.execute("UPDATE communication_messages SET status='Approved',approval_notes=?,approved_at=?,updated_at=? WHERE id=?",
          (str(payload.get("notes",""))+" | Approved by: "+approver,stamp(),stamp(),message_id))
        c.execute("INSERT INTO communication_events(message_id,event_type,details,created_at) VALUES(?,?,?,?)",(message_id,"Approved","Approved by "+approver,stamp()))
    return {"id":message_id,"status":"Approved","message":"Approved. Recru Agent has not sent the message."}

@router.post("/messages/{message_id}/mark-manually-sent")
def mark_manually_sent(message_id:int,payload:dict):
    if not payload.get("confirmed_manual_send"):
        raise HTTPException(400,"Confirm that you sent the approved message manually before recording it.")
    messages=rows("SELECT m.status,m.channel,c.do_not_contact,c.contact_preference FROM communication_messages m JOIN candidates c ON c.id=m.candidate_id WHERE m.id=?",(message_id,))
    if not messages: raise HTTPException(404,"Message draft not found.")
    if messages[0]["do_not_contact"] or messages[0]["contact_preference"]=="Do not contact": raise HTTPException(409,"Candidate is marked Do not contact.")
    if messages[0]["contact_preference"] in ("Email","LinkedIn","Phone") and messages[0]["contact_preference"]!=messages[0]["channel"]: raise HTTPException(409,"Candidate contact preference no longer matches this message channel.")
    if messages[0]["status"]!="Approved": raise HTTPException(409,"Only an approved message can be marked manually sent.")
    with connect() as c:
        c.execute("UPDATE communication_messages SET status='Manually Sent',manually_sent_at=?,updated_at=? WHERE id=?",(stamp(),stamp(),message_id))
        c.execute("INSERT INTO communication_events(message_id,event_type,details,created_at) VALUES(?,?,?,?)",(message_id,"Marked manually sent","Recruiter confirmed manual send.",stamp()))
    return {"id":message_id,"status":"Manually Sent","message":"Manual send recorded. No message was sent by Recru Agent."}

@router.post("/messages/{message_id}/cancel")
def cancel_message(message_id:int):
    messages=rows("SELECT status FROM communication_messages WHERE id=?",(message_id,))
    if not messages: raise HTTPException(404,"Message draft not found.")
    if messages[0]["status"] in ("Manually Sent","Cancelled"): raise HTTPException(409,"This message cannot be cancelled.")
    with connect() as c:
        c.execute("UPDATE communication_messages SET status='Cancelled',updated_at=? WHERE id=?",(stamp(),message_id))
        c.execute("INSERT INTO communication_events(message_id,event_type,details,created_at) VALUES(?,?,?,?)",(message_id,"Cancelled","Recruiter cancelled the message.",stamp()))
    return {"id":message_id,"status":"Cancelled"}
