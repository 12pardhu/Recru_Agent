import json, os, re, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR",str(ROOT/"data")))
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/"recru_agent.db"
router=APIRouter(prefix="/api/qualification",tags=["Candidate Qualification"])

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def stamp():
    return datetime.now(timezone.utc).isoformat()

def rows(sql,args=()):
    with connect() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]

def tokens(value):
    return [x.strip() for x in re.split(r"[,;\n|]",value or "") if x.strip()]

def init():
    with connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS qualification_records(
          id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, candidate_id INTEGER NOT NULL,
          result_json TEXT NOT NULL, overall_status TEXT NOT NULL,
          recruiter_decision TEXT NOT NULL DEFAULT 'Pending', recruiter_notes TEXT DEFAULT '',
          evaluated_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
init()

def evaluate(job,candidate):
    required=tokens(job.get("skills",""))
    preferred=tokens(job.get("preferred_skills",""))
    candidate_skills={x.lower() for x in tokens(candidate.get("skills",""))}
    matched=[x for x in required if x.lower() in candidate_skills]
    missing=[x for x in required if x.lower() not in candidate_skills]
    criteria=[]

    min_exp=job.get("min_experience")
    exp=candidate.get("experience") or 0
    if min_exp is None:
        criteria.append({"criterion":"Total experience","status":"Not specified","required":None,"candidate_value":exp,"evidence":"The job requirement does not state a minimum."})
    elif not exp:
        criteria.append({"criterion":"Total experience","status":"Unknown","required":min_exp,"candidate_value":None,"evidence":"Candidate experience is not recorded."})
    elif exp>=min_exp:
        criteria.append({"criterion":"Total experience","status":"Potential match — verify","required":min_exp,"candidate_value":exp,"evidence":"Experience is recorded in the candidate profile; confirm dates and relevance."})
    else:
        criteria.append({"criterion":"Total experience","status":"Does not meet","required":min_exp,"candidate_value":exp,"evidence":"Recorded experience is below the stated minimum; verify before any decision."})

    if not required:
        criteria.append({"criterion":"Mandatory skills","status":"Not specified","required":[],"candidate_value":tokens(candidate.get("skills","")),"evidence":"No mandatory skills were saved for this job."})
    elif not candidate_skills:
        criteria.append({"criterion":"Mandatory skills","status":"Unknown","required":required,"candidate_value":[],"evidence":"Candidate skills are not recorded."})
    elif not missing:
        criteria.append({"criterion":"Mandatory skills","status":"Potential match — verify","required":required,"candidate_value":matched,"evidence":"Skills appear in the candidate record or resume; recruiter must verify proficiency and recency."})
    elif matched:
        criteria.append({"criterion":"Mandatory skills","status":"Partial match","required":required,"candidate_value":matched,"missing":missing,"evidence":"Some mandatory skills are not present in the candidate record."})
    else:
        criteria.append({"criterion":"Mandatory skills","status":"Does not meet","required":required,"candidate_value":[],"missing":missing,"evidence":"No mandatory skills were found in the candidate record."})

    locs=tokens(job.get("location",""))
    cand_loc=(candidate.get("location") or "").lower()
    if not locs:
        criteria.append({"criterion":"Location","status":"Not specified","required":[],"candidate_value":candidate.get("location",""),"evidence":"The job has no saved location restriction."})
    elif not cand_loc:
        criteria.append({"criterion":"Location","status":"Unknown","required":locs,"candidate_value":"","evidence":"Candidate location is not recorded."})
    elif any(loc.lower() in cand_loc or cand_loc in loc.lower() for loc in locs):
        criteria.append({"criterion":"Location","status":"Potential match — verify","required":locs,"candidate_value":candidate.get("location"),"evidence":"Recorded location appears to match; confirm current location and commute/relocation."})
    else:
        criteria.append({"criterion":"Location","status":"Needs recruiter review","required":locs,"candidate_value":candidate.get("location"),"evidence":"Recorded location differs from the job location. Confirm remote/relocation flexibility."})

    job_auth=[x.lower() for x in tokens(job.get("work_auth","")) if x.lower()!="unknown"]
    cand_auth=candidate.get("work_auth") or "Unknown"
    auth_confirmed=candidate.get("work_auth_confirmed")=="Candidate confirmed"
    if not job_auth:
        criteria.append({"criterion":"Work authorization","status":"Not specified","required":[],"candidate_value":"Not evaluated","evidence":"The job does not state an authorization requirement."})
    elif not auth_confirmed or cand_auth=="Unknown":
        criteria.append({"criterion":"Work authorization","status":"Unknown","required":job_auth,"candidate_value":"Unknown","evidence":"Candidate has not confirmed work authorization. Do not infer it from a resume or profile."})
    else:
        cand_norm=cand_auth.lower()
        auth_match=cand_norm in job_auth or ("opt" in job_auth and cand_norm=="stem opt") or "any us work authorization" in job_auth
        criteria.append({"criterion":"Work authorization","status":"Meets — candidate confirmed" if auth_match else "Does not meet","required":job_auth,"candidate_value":cand_auth,"evidence":"Candidate-confirmed value recorded in the candidate profile."})

    employment=[x.lower() for x in tokens(job.get("employment_type","")) if x.lower()!="unknown"]
    if "c2c" in employment:
        c2c_confirmed=candidate.get("c2c_confirmed")=="Candidate confirmed"
        c2c=candidate.get("c2c_status") or "Unknown"
        if not c2c_confirmed or c2c=="Unknown":
            status="Unknown"
            evidence="C2C has not been confirmed by the candidate."
        elif c2c=="Confirmed":
            status="Meets — candidate confirmed"; evidence="Candidate confirmed C2C availability."
        else:
            status="Does not meet"; evidence="Candidate confirmed C2C is not available."
        criteria.append({"criterion":"C2C availability","status":status,"required":"C2C","candidate_value":c2c,"evidence":evidence})
    elif employment:
        criteria.append({"criterion":"Employment type","status":"Needs recruiter review","required":employment,"candidate_value":"Not recorded","evidence":"Confirm the candidate's acceptable engagement type before proceeding."})
    else:
        criteria.append({"criterion":"Employment type","status":"Not specified","required":[],"candidate_value":"Not evaluated","evidence":"The job does not state an employment type."})

    preferred_matches=[x for x in preferred if x.lower() in candidate_skills]
    criteria.append({"criterion":"Preferred skills","status":"Informational","required":preferred,"candidate_value":preferred_matches,"missing":[x for x in preferred if x not in preferred_matches],"evidence":"Preferred skills are informational and are not treated as mandatory."})
    availability=candidate.get("availability_signal") or "Unknown"
    criteria.append({"criterion":"Candidate-reported availability","status":"Informational","required":"Candidate confirmation","candidate_value":availability,"evidence":"Open to Work is a profile signal only; confirm interest and availability directly."})

    hard=[x for x in criteria if x["criterion"] in ("Total experience","Mandatory skills","Work authorization","C2C availability")]
    if any(x["status"]=="Does not meet" for x in hard):
        overall="Potential blocker — recruiter decision required"
    elif any(x["status"] in ("Unknown","Partial match","Needs recruiter review","Potential match — verify") for x in criteria):
        overall="Needs recruiter review"
    else:
        overall="Potentially aligned — verify before proceeding"
    provenance={
      "source_type":candidate.get("source_type","Unknown"),
      "source_url":candidate.get("source_url",""),
      "source_evidence":candidate.get("source_evidence",""),
      "resume_attached":bool(candidate.get("resume_draft_id"))
    }
    return {"overall_status":overall,"criteria":criteria,"matched_mandatory_skills":matched,
      "missing_mandatory_skills":missing,"preferred_skill_matches":preferred_matches,
      "provenance":provenance,"notice":"This is an evidence-based screening aid, not an automated hiring decision. Recruiter verification is required."}

@router.post("/jobs/{job_id}/evaluate")
def evaluate_job_candidates(job_id:int):
    jobs=rows("SELECT * FROM jobs WHERE id=?",(job_id,))
    if not jobs: raise HTTPException(404,"Job requirement not found.")
    if not rows("SELECT id FROM job_versions WHERE job_id=? LIMIT 1",(job_id,)):
        raise HTTPException(409,"Confirm the job requirement before qualification.")
    candidates=rows("SELECT * FROM candidates ORDER BY id")
    created=[]
    with connect() as c:
        for candidate in candidates:
            result=evaluate(jobs[0],candidate)
            cur=c.execute("INSERT INTO qualification_records(job_id,candidate_id,result_json,overall_status,recruiter_decision,recruiter_notes,evaluated_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
              (job_id,candidate["id"],json.dumps(result),result["overall_status"],"Pending","",stamp(),stamp()))
            created.append(cur.lastrowid)
    return {"job_id":job_id,"evaluated_count":len(created),"message":"Qualification recommendations prepared. Every candidate requires recruiter review."}

@router.get("/jobs/{job_id}")
def get_job_qualifications(job_id:int):
    return rows("""SELECT q.*,c.name candidate_name,c.location candidate_location,c.experience candidate_experience
      FROM qualification_records q JOIN candidates c ON c.id=q.candidate_id
      WHERE q.job_id=? AND q.id=(SELECT MAX(q2.id) FROM qualification_records q2 WHERE q2.job_id=q.job_id AND q2.candidate_id=q.candidate_id)
      ORDER BY q.id DESC""",(job_id,))

@router.get("/{record_id}")
def get_qualification(record_id:int):
    records=rows("""SELECT q.*,c.name candidate_name,j.title job_title
      FROM qualification_records q JOIN candidates c ON c.id=q.candidate_id JOIN jobs j ON j.id=q.job_id
      WHERE q.id=?""",(record_id,))
    if not records: raise HTTPException(404,"Qualification record not found.")
    records[0]["result"]=json.loads(records[0].pop("result_json"))
    return records[0]

@router.patch("/{record_id}")
def update_qualification_review(record_id:int,payload:dict):
    decision=payload.get("recruiter_decision")
    allowed=("Pending","Proceed to Screening","Hold","Not a Fit","Needs More Information")
    if decision not in allowed: raise HTTPException(400,"Choose a valid recruiter review decision.")
    with connect() as c:
        cur=c.execute("UPDATE qualification_records SET recruiter_decision=?,recruiter_notes=?,updated_at=? WHERE id=?",
          (decision,str(payload.get("recruiter_notes","")),stamp(),record_id))
        if not cur.rowcount: raise HTTPException(404,"Qualification record not found.")
    return {"id":record_id,"recruiter_decision":decision,"message":"Recruiter review saved."}
