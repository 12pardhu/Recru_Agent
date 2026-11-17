# Recru Agent — AI OPT Recruiter Agent V2 Ultimate

A cloud-ready recruiter-assist prototype for US IT staffing. Upload/paste a job requirement, maintain a candidate list, compare candidates against job skills/experience/location, and route shortlisted candidates for recruiter approval.

## Features
- Job requirement intake (paste JD or read a TXT/MD file).
- Candidate CRM with experience, skills, location, work authorization, C2C confirmation, and LinkedIn URL fields.
- Explainable skills/experience/location matching.
- Recruiter approval queue; no automated outreach or submission.
- SQLite starter database and FastAPI API.
- Single-page browser UI; no Docker or Node.js required to run/deploy this version.

## Run locally
Python 3.10+ recommended.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
``
Open http://127.0.0.1:8000.

## Cloud
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). A Render Blueprint is provided in `render.yaml`.

## Important limitations
This is a reconstructed V2 starter and not the previously tested React/PostgreSQL build. PDF/DOCX parsing, bulk CSV import/export, authentication, tenant isolation, and automated LinkedIn sourcing are not included. Matching is advisory only. Read [docs/SAFE_USE.md](docs/SAFE_USE.md).

**Security warning:** No login or access control is included. Do not expose publicly or use real candidate PII until production security and privacy controls are implemented. Render free local storage may be ephemeral.
