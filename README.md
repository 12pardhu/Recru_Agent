# Recru Agent — Candidate Sourcing & Matching

Cloud-hosted recruiter-assist prototype for US IT staffing. Upload a JD, review extracted requirements, prepare LinkedIn People searches, capture recruiter-reviewed candidate profiles, rank candidates, and route them for human approval.

## Included
- JD intake from pasted text or TXT, MD, PDF, DOCX files.
- Transparent rule-based extraction of title, domain, skills, experience, location and work authorization (review before saving).
- Both sourcing workflows: automatic search-plan preparation after JD save, plus recruiter-triggered refresh/open search.
- LinkedIn People search URL generation. This does not scrape LinkedIn or fetch private profile data.
- Candidate CRM with Open to Work and availability signals, source/evidence fields, and duplicate checks by email/profile URL.
- Explainable prototype matching across skills, experience, location, authorization evidence, preferred skills and availability priority.
- Recruiter approval queue and CSV export.
- SQLite starter storage; no Docker or Node.js required.

## Run locally
Python 3.10+:
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
Open http://127.0.0.1:8000.

## Cloud
Render Blueprint is in render.yaml. The current free service filesystem may be ephemeral; configure a managed persistent database/disk before operational use.

## Not production-ready
No login, RBAC, tenant isolation, persistent managed database, or LinkedIn API integration is included. Do not use real candidate PII or resumes until security/privacy controls are implemented. Matching is advisory only; recruiters must verify candidate statements and approve every next step.