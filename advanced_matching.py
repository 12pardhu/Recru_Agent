import json, os, re, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR",str(ROOT/"data")))
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/"recru_agent.db"
router=APIRouter(prefix="/api/matching",tags=["Advanced Candidate Matching"])

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def stamp():
    return datetime.now(timezone.utc).isoformat()

def rows(sql,args=()):
    with connect() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]

def tokens(value):
    return [x.strip() for x in re.split(r"[,;\n|]",value or "") if x.strip()]

ALIASES={
 "springboot":"spring boot","spring framework":"spring boot",
 "restful":"rest api","rest apis":"rest api","restapi":"rest api","rest":"rest api",
 "postgres":"postgresql","k8s":"kubernetes","amazon web services":"aws",
 "ml":"machine learning","gen ai":"genai","node":"node.js"
}
def norm_skill(value):
    key=re.sub(r"\s+"," ",value.lower().replace("_"," ").strip())
    return ALIASES.get(key.replace(" ",""),ALIASES.get(key,key))

def skill_set(value):
    return {norm_skill(x) for x in tokens(value)}

def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS match_runs(
          id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, algorithm_version TEXT NOT NULL,
          created_at TEXT NOT NULL, candidate_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS match_results(
          id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, job_id INTEGER NOT NULL,
          candidate_id INTEGER NOT NULL, score REAL NOT NULL, band TEXT NOT NULL,
          result_json TEXT NOT NULL, recruiter_decision TEXT NOT NULL DEFAULT 'Pending',
          recruiter_notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """)
init()

def score_candidate(job,candidate):
    required=tokens(job.get("skills",""))
    preferred=tokens(job.get("preferred_skills",""))
    cskills=skill_set(candidate.get("skills",""))
    criteria=[]
    weighted_points=0.0; available_weight=0.0

    def add(name,weight,points,status,evidence):
        nonlocal weighted_points,available_weight
        available_weight+=weight; weighted_points+=points
        criteria.append({"criterion":name,"weight":weight,"points":round(points,2),"status":status,"evidence":evidence})

    if required:
        matched=[x for x in required if norm_skill(x) in cskills]
        points=40*len(matched)/len(required)
        missing=[x for x in required if norm_skill(x) not in cskills]
        status=str(len(matched))+"/"+str(len(required))+" mandatory skills appear in the candidate record"
        add("Mandatory skills",40,points,status,"Matched: "+(", ".join(matched) or "None")+". Missing from record: "+(", ".join(missing) or "None")+". Resume/profile presence is not proof of proficiency.")
    min_exp=job.get("min_experience")
    exp=candidate.get("experience") or 0
    if min_exp is not None and min_exp>0:
        points=15*min(1.0,float(exp)/float(min_exp)) if exp else 0
        status=("Recorded experience meets or exceeds minimum" if exp>=min_exp and exp else ("Recorded experience is below minimum" if exp else "Experience unknown"))
        add("Total experience",15,points,status,"Candidate record: "+(str(exp)+" years" if exp else "Unknown")+"; job minimum: "+str(min_exp)+" years. Confirm dates and relevant experience.")
    locations=[x.strip() for x in re.split(r"[;|]",job.get("location","") or "") if x.strip()]
    if locations:
        candidate_location=candidate.get("location") or ""
        norm_candidate=re.sub(r"[^a-z0-9]","",candidate_location.lower())
        matched_location=next((x for x in locations if re.sub(r"[^a-z0-9]","",x.lower()) in norm_candidate or norm_candidate in re.sub(r"[^a-z0-9]","",x.lower())),None) if norm_candidate else None
        points=10 if matched_location else 0
        add("Location",10,points,"Potential location match" if matched_location else ("Candidate location unknown" if not candidate_location else "Location requires recruiter review"),"Job locations: "+", ".join(locations)+". Candidate location: "+(candidate_location or "Unknown")+". Confirm current location and work arrangement.")
    job_auth=[x.lower() for x in tokens(job.get("work_auth","")) if x.lower()!="unknown"]
    if job_auth:
        auth=candidate.get("work_auth") or "Unknown"
        confirmed=candidate.get("work_auth_confirmed")=="Candidate confirmed"
        match=confirmed and (auth.lower() in job_auth or ("opt" in job_auth and auth.lower()=="stem opt") or "any us work authorization" in job_auth)
        points=15 if match else 0
        status="Candidate-confirmed authorization matches" if match else ("Candidate-confirmed authorization differs" if confirmed and auth!="Unknown" else "Authorization not candidate-confirmed")
        add("Work authorization",15,points,status,"Required: "+", ".join(job_auth)+". Candidate: "+(auth if confirmed else "Unknown — confirmation required")+".")
    employment=[x.lower() for x in tokens(job.get("employment_type","")) if x.lower()!="unknown"]
    if employment:
        pref=candidate.get("employment_preference") or "Unknown"
        confirmed=candidate.get("employment_preference_confirmed")=="Candidate confirmed"
        c2c_ok=candidate.get("c2c_confirmed")=="Candidate confirmed" and candidate.get("c2c_status")=="Confirmed"
        match=confirmed and (pref.lower()=="both" or pref.lower() in employment)
        if not match and "c2c" in employment and c2c_ok: match=True
        points=10 if match else 0
        status="Candidate-confirmed engagement type matches" if match else ("Engagement type not confirmed" if not confirmed and not c2c_ok else "Candidate-confirmed engagement type differs")
        add("Employment type",10,points,status,"Required: "+", ".join(employment)+". Candidate preference: "+(pref if confirmed else ("C2C confirmed" if c2c_ok else "Unknown"))+".")
    if preferred:
        matched_pref=[x for x in preferred if norm_skill(x) in cskills]
        points=5*len(matched_pref)/len(preferred)
        add("Preferred skills",5,points,str(len(matched_pref))+"/"+str(len(preferred))+" preferred skills appear in the record","Matched: "+(", ".join(matched_pref) or "None")+". Preferred skills are not mandatory.")
    availability=candidate.get("availability_signal") or "Unknown"
    points={"Actively looking":5,"Interested":3.5,"Not looking":0}.get(availability,0)
    add("Candidate-reported availability",5,points,availability,"Use candidate-reported availability only. Open to Work profile signals are not treated as availability confirmation.")
    score=round((weighted_points/available_weight)*100) if available_weight>=20 else 0
    band=("Insufficient job criteria" if available_weight<20 else ("Strong evidence alignment" if score>=80 else ("Potential alignment" if score>=65 else ("Partial evidence alignment" if score>=45 else "Low or insufficient evidence"))))
    return {"score":score,"band":band,"available_weight":available_weight,"criteria":criteria,"recommendation":("Add more explicit job criteria before using this score." if available_weight<20 else "Recruiter review required — do not auto-reject or submit."),
      "matched_mandatory_skills":[x for x in required if norm_skill(x) in cskills],
      "missing_mandatory_skills":[x for x in required if norm_skill(x) not in cskills],
      "provenance":{"source_type":candidate.get("source_type","Unknown"),"source_url":candidate.get("source_url",""),
        "source_evidence":candidate.get("source_evidence",""),"resume_attached":bool(candidate.get("resume_draft_id"))},
      "notice":"This is a transparent rule-based score, not an AI guarantee or hiring decision. Verify all candidate statements."}

@router.post("/jobs/{job_id}/run")
def run_matching(job_id:int):
    jobs=rows("SELECT * FROM jobs WHERE id=?",(job_id,))
    if not jobs: raise HTTPException(404,"Job requirement not found.")
    if not rows("SELECT id FROM job_versions WHERE job_id=? LIMIT 1",(job_id,)):
        raise HTTPException(409,"Confirm the job requirement before matching candidates.")
    candidates=rows("SELECT * FROM candidates ORDER BY id")
    with connect() as c:
        cur=c.execute("INSERT INTO match_runs(job_id,algorithm_version,created_at,candidate_count) VALUES(?,?,?,?)",(job_id,"explainable-v1",stamp(),len(candidates)))
        run_id=cur.lastrowid
        for candidate in candidates:
            result=score_candidate(jobs[0],candidate)
            c.execute("INSERT INTO match_results(run_id,job_id,candidate_id,score,band,result_json,recruiter_decision,recruiter_notes,created_at,updated_at) VALUES(?,?,?,?,?,?,'Pending','',?,?)",
              (run_id,job_id,candidate["id"],result["score"],result["band"],json.dumps(result),stamp(),stamp()))
    return {"run_id":run_id,"job_id":job_id,"candidate_count":len(candidates),"algorithm_version":"explainable-v1","message":"Explainable matching completed. Recruiter review is required."}

@router.get("/jobs/{job_id}/latest")
def latest_matching(job_id:int):
    runs=rows("SELECT * FROM match_runs WHERE job_id=? ORDER BY id DESC LIMIT 1",(job_id,))
    if not runs: return {"job_id":job_id,"run":None,"results":[]}
    run=runs[0]
    results=rows("""SELECT r.*,c.name candidate_name,c.location candidate_location,c.experience candidate_experience
      FROM match_results r JOIN candidates c ON c.id=r.candidate_id WHERE r.run_id=? ORDER BY r.score DESC,r.id""",(run["id"],))
    return {"job_id":job_id,"run":run,"results":results}

@router.get("/runs/{run_id}")
def get_run(run_id:int):
    runs=rows("SELECT * FROM match_runs WHERE id=?",(run_id,))
    if not runs: raise HTTPException(404,"Matching run not found.")
    results=rows("SELECT * FROM match_results WHERE run_id=? ORDER BY score DESC",(run_id,))
    for result in results: result["result"]=json.loads(result.pop("result_json"))
    return {"run":runs[0],"results":results}

@router.patch("/results/{result_id}")
def update_match_review(result_id:int,payload:dict):
    decision=payload.get("recruiter_decision")
    allowed=("Pending","Shortlist for Screening","Hold","Not a Match","Needs More Information")
    if decision not in allowed: raise HTTPException(400,"Choose a valid recruiter review decision.")
    with connect() as c:
        cur=c.execute("UPDATE match_results SET recruiter_decision=?,recruiter_notes=?,updated_at=? WHERE id=?",
          (decision,str(payload.get("recruiter_notes","")),stamp(),result_id))
        if not cur.rowcount: raise HTTPException(404,"Matching result not found.")
    return {"id":result_id,"recruiter_decision":decision,"message":"Recruiter matching review saved."}
