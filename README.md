# Recru Agent

Cloud-hosted recruiter-assist application for US IT staffing. The product is being developed in 12 milestones. The current development branch contains the in-progress **Milestone 1 — Job Requirement Intelligence** implementation.

## Milestone 1: Job Requirement Intelligence

- Create JD drafts by uploading PDF, DOCX, TXT, or MD files, or by pasting JD text.
- Preserve uploaded originals in the configured data directory and provide a download link from the draft review screen.
- Extract structured fields using transparent rule-based parsing: title, domain, locations, total and relevant experience, technology-specific experience, mandatory/preferred/optional skills, technology versions, work authorization, employment type, rate, work arrangement, responsibilities, education, certifications, travel, and relocation.
- Display field evidence/statuses and allow recruiter edits before confirmation.
- Run a quality check that identifies missing information and selected conflicts. Warnings require explicit recruiter acknowledgement; blocking title issues prevent confirmation.
- Confirmed requirements are saved with a version snapshot. Recruiters can create a revision draft and inspect version history.
- Sourcing and candidate matching require a confirmed requirement. Confirmation itself does not launch sourcing.

**Important:** extraction is deterministic rule/keyword parsing, not a connected LLM or external AI service. It is an assistive first pass, not a substitute for recruiter review. Unknown information must remain unknown.

## Existing recruiter-assist features

- Prepare LinkedIn People Search URLs for the recruiter to open in their authorized LinkedIn session.
- The app does not scrape LinkedIn, bypass access controls, or automatically collect private profile data.
- Candidate CRM, duplicate checks, matching recommendations, approval queue, and CSV export are prototype features.
- Candidate work authorization, C2C, availability, and Open to Work must be verified with the candidate; profile signals are not proof.

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

Render Blueprint is in `render.yaml`. The free service filesystem may be ephemeral; configure a managed persistent database/disk before operational use. Do not assume uploaded JD files or SQLite data survive service restarts/redeployments on an ephemeral filesystem.

## Not production-ready

No login, role-based access control, tenant isolation, managed persistent database, or full privacy/retention controls are included. Use fictional data only until security and privacy safeguards are implemented. Matching is advisory only; recruiters must verify candidate statements and approve every next step.

## Development roadmap

1. Job Requirement Intelligence
2. Candidate Sourcing Intelligence
3. Resume Intelligence
4. Candidate Qualification
5. Candidate Communication
6. OPT Recruiter Screening
7. Advanced AI Matching
8. Client Submission Management
9. Interview Management
10. Recruitment Pipeline
11. Recruiter Productivity Dashboard
12. Security, Quality and Release

Milestone 1 remains under development until implementation, integration, and the later deferred test/sign-off stage are complete.
