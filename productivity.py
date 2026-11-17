import os, sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR",str(ROOT/"data")))
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/"recru_agent.db"
router=APIRouter(prefix="/api/productivity",tags=["Recruiter Productivity"])

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def rows(sql,args=()):
    with connect() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]

def scalar(sql,args=()):
    with connect() as c:
        r=c.execute(sql,args).fetchone()
        return r[0] if r else 0

def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()

@router.get("/overview")
def productivity_overview(period_days:int=30):
    if period_days not in (7,30,90,365):
        raise HTTPException(400,"Choose a reporting period of 7, 30, 90, or 365 days.")
    now=datetime.now(timezone.utc)
    start=iso(now-timedelta(days=period_days))
    end=iso(now)
    counts={
      "new_jobs":scalar("SELECT COUNT(*) FROM jobs WHERE created_at>=?",(start,)),
      "new_candidates":scalar("SELECT COUNT(*) FROM candidates WHERE created_at>=?",(start,)),
      "sourcing_tasks":scalar("SELECT COUNT(*) FROM sourcing_tasks WHERE created_at>=?",(start,)),
      "pending_approvals":scalar("SELECT COUNT(*) FROM approvals WHERE status='Pending'"),
      "active_pipeline":scalar("SELECT COUNT(*) FROM recruitment_pipeline WHERE stage_status IN ('Active','Waiting')"),
      "completed_screenings":scalar("SELECT COUNT(*) FROM screening_sessions WHERE status='Completed' AND completed_at>=?",(start,)),
      "client_submissions":scalar("SELECT COUNT(*) FROM client_submissions WHERE submitted_at>=? AND submitted_at<>''",(start,)),
      "interviews":scalar("SELECT COUNT(*) FROM interviews WHERE created_at>=?",(start,))
    }
    stages=rows("SELECT current_stage AS stage,COUNT(*) AS count FROM recruitment_pipeline GROUP BY current_stage ORDER BY CASE current_stage WHEN 'Sourcing' THEN 1 WHEN 'Qualification' THEN 2 WHEN 'Screening' THEN 3 WHEN 'Client Submission' THEN 4 WHEN 'Interview' THEN 5 WHEN 'Offer' THEN 6 WHEN 'Placed' THEN 7 WHEN 'Rejected' THEN 8 ELSE 9 END")
    statuses=rows("SELECT stage_status AS status,COUNT(*) AS count FROM recruitment_pipeline GROUP BY stage_status ORDER BY stage_status")
    decisions=rows("SELECT recruiter_decision AS decision,COUNT(*) AS count FROM qualification_records WHERE evaluated_at>=? GROUP BY recruiter_decision ORDER BY recruiter_decision",(start,))
    submissions=rows("SELECT status,COUNT(*) AS count FROM client_submissions GROUP BY status ORDER BY status")
    interview_outcomes=rows("SELECT outcome,COUNT(*) AS count FROM interviews WHERE outcome<>'' GROUP BY outcome ORDER BY outcome")
    sourcing=rows("""SELECT s.id,s.status,s.target_count,s.created_at,j.title AS job_title,
      (SELECT COUNT(*) FROM candidates c WHERE c.sourcing_task_id=s.id) AS candidates_added
      FROM sourcing_tasks s JOIN jobs j ON j.id=s.job_id ORDER BY s.created_at DESC LIMIT 10""")
    pipeline=rows("""SELECT p.id,p.current_stage,p.stage_status,p.owner,p.next_action,p.due_at,p.updated_at,
      c.name AS candidate_name,j.title AS job_title
      FROM recruitment_pipeline p JOIN candidates c ON c.id=p.candidate_id
      JOIN jobs j ON j.id=p.job_id ORDER BY p.updated_at DESC""")
    # Only offset-aware due dates can be compared across time zones reliably.
    overdue=[]; upcoming=[]
    for item in pipeline:
        if not item["due_at"] or item["stage_status"]=="Completed": continue
        try:
            due=datetime.fromisoformat(item["due_at"].replace("Z","+00:00"))
            if due.tzinfo is None: continue
            if due.astimezone(timezone.utc)<now: overdue.append(item)
            elif due.astimezone(timezone.utc)<=now+timedelta(days=7): upcoming.append(item)
        except ValueError:
            continue
    recent=[]
    event_queries=[
      ("Pipeline","""SELECT e.created_at,e.event_type,e.details,c.name AS person,j.title AS role
        FROM pipeline_events e JOIN recruitment_pipeline p ON p.id=e.pipeline_id
        JOIN candidates c ON c.id=p.candidate_id JOIN jobs j ON j.id=p.job_id"""),
      ("Sourcing","""SELECT e.created_at,e.event_type,e.details,'' AS person,j.title AS role
        FROM sourcing_events e JOIN sourcing_tasks s ON s.id=e.task_id JOIN jobs j ON j.id=s.job_id"""),
      ("Screening","""SELECT e.created_at,e.event_type,e.details,c.name AS person,j.title AS role
        FROM screening_events e JOIN screening_sessions s ON s.id=e.session_id
        JOIN candidates c ON c.id=s.candidate_id JOIN jobs j ON j.id=s.job_id"""),
      ("Qualification","""SELECT e.created_at,e.event_type,e.details,c.name AS person,j.title AS role
        FROM qualification_events e JOIN qualification_records q ON q.id=e.record_id
        JOIN candidates c ON c.id=q.candidate_id JOIN jobs j ON j.id=q.job_id"""),
      ("Submission","""SELECT e.created_at,e.event_type,e.details,c.name AS person,j.title AS role
        FROM submission_events e JOIN client_submissions s ON s.id=e.submission_id
        JOIN candidates c ON c.id=s.candidate_id JOIN jobs j ON j.id=s.job_id"""),
      ("Interview","""SELECT e.created_at,e.event_type,e.details,c.name AS person,j.title AS role
        FROM interview_events e JOIN interviews i ON i.id=e.interview_id
        JOIN client_submissions s ON s.id=i.submission_id JOIN candidates c ON c.id=s.candidate_id
        JOIN jobs j ON j.id=s.job_id"""),
      ("Communication","""SELECT e.created_at,e.event_type,e.details,c.name AS person,COALESCE(j.title,'') AS role
        FROM communication_events e JOIN communication_messages m ON m.id=e.message_id
        JOIN candidates c ON c.id=m.candidate_id LEFT JOIN jobs j ON j.id=m.job_id""")
    ]
    for category,query in event_queries:
        for item in rows(query+" WHERE e.created_at>=?",(start,)):
            item["category"]=category; recent.append(item)
    recent.sort(key=lambda x:x["created_at"],reverse=True)
    workload=rows("""SELECT CASE WHEN owner='' THEN 'Unassigned' ELSE owner END AS owner,
      COUNT(*) AS records,SUM(CASE WHEN stage_status IN ('Active','Waiting') THEN 1 ELSE 0 END) AS open_records
      FROM recruitment_pipeline GROUP BY owner ORDER BY records DESC""")
    return {
      "period_days":period_days,"generated_at":end,"counts":counts,
      "pipeline_stages":stages,"pipeline_statuses":statuses,
      "qualification_decisions":decisions,"submission_statuses":submissions,
      "interview_outcomes":interview_outcomes,"sourcing_recent":sourcing,
      "overdue_actions":overdue[:25],"upcoming_actions":upcoming[:25],
      "recruiter_workload":workload,"recent_activity":recent[:30],
      "notes":["Overdue/upcoming pipeline actions are calculated only when due dates include a time-zone offset. Local times without an offset are shown in the pipeline but excluded from these calculations.","Metrics summarize recorded workflow activity; they are not a measure of recruiter quality or candidate suitability."]
    }
