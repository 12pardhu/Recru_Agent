# Recru Agent

Cloud-hosted recruiter-assist application for US IT staffing. The development branch now contains application implementations for all 12 milestones, including job requirement intelligence, sourcing, resume intelligence, qualification, communication, OPT screening, matching, client submissions, interviews, recruitment pipeline, productivity reporting, and application-level security/privacy controls. Runtime verification and the formal test suite are intentionally deferred until the development build is complete. Production release remains blocked on persistent managed storage, deployment hardening, formal security review, and release sign-off.

## Milestone 1: Job Requirement Intelligence

- Create JD drafts by uploading PDF, DOCX, TXT, or MD files, or by pasting JD text.
- Preserve uploaded originals in the configured data directory and provide a download link from the draft review screen.
- Extract structured fields using transparent rule-based parsing: title, domain, locations, total and relevant experience, technology-specific experience, mandatory/preferred/optional skills, technology versions, work authorization, employment type, rate, work arrangement, responsibilities, education, certifications, travel, and relocation.
- Display field evidence/statuses and allow recruiter edits before confirmation.
- Run a quality check that identifies missing information and selected conflicts. Warnings require explicit recruiter acknowledgement; blocking title issues prevent confirmation.
- Confirmed requirements are saved with a version snapshot. Recruiters can create a revision draft and inspect version history.
- Sourcing and candidate matching require a confirmed requirement. Confirmation itself does not launch sourcing.

**Important:** extraction is deterministic rule/keyword parsing, not a connected LLM or external AI service. It is an assistive first pass, not a substitute for recruiter review. Unknown information must remain unknown.

## Milestone 2: Candidate Sourcing Intelligence (in development)

- Generate focused LinkedIn People search variants for each JD location: role, skills, and authorization hints where stated.
- Set a recruiter-controlled daily sourcing target (50–100 candidates per task).
- Track each location/search variant as Prepared, In Progress, Completed, or Skipped.
- Track sourcing task status, target count, recruiter notes, candidate count, timestamps, and activity history.
- Capture candidate records manually after recruiter review in an authorized LinkedIn session.
- Link each candidate to the sourcing task and preserve source type, URL, evidence notes, and capture activity.
- Detect duplicate candidate email/profile URLs before saving.
- Require candidate confirmation before recording OPT/STEM OPT or other work authorization as confirmed; require candidate confirmation for C2C yes/no.
- Do not scrape LinkedIn or automatically extract profile data. Open to Work remains a profile signal, not proof of candidate availability.

## Milestone 3: Resume Intelligence (in development)

- Upload PDF, DOCX, TXT, or MD resumes (15 MB maximum), or paste resume text.
- Extract candidate name, email, phone, labelled location, experience, skills, education, certifications, work history, projects, summary, and profile links.
- Preserve the original uploaded resume and allow recruiter download.
- Show field evidence and missing-field warnings; recruiter reviews and edits the candidate form before saving.
- Attach the reviewed resume draft to a candidate record and expose the attached original resume in the candidate database.
- Resume parsing does not infer or confirm OPT/STEM OPT, other work authorization, C2C status, Open to Work, or availability.

**Important:** resume extraction is rule-based and may miss content in scanned PDFs, complex layouts, columns, images, or unusual resume formats. OCR is not included. Human review is required.

## Milestone 4: Candidate Qualification (in development)

- Compare a candidate record with a confirmed job requirement using transparent criterion-level rules.
- Review total experience, mandatory and preferred skills, location, candidate-confirmed work authorization, and candidate-confirmed C2C/W2 engagement preference.
- Display Potential match, Partial match, Unknown, Not specified, Needs recruiter review, and potential blocker statuses with evidence/provenance.
- Missing resume skills are not treated as proof that a candidate lacks a skill. Resume-stated experience and skills remain subject to verification.
- Save recruiter decisions and notes: Proceed to Screening, Hold, Not a Fit, or Needs More Information.
- Record qualification generation and recruiter-decision activity history.
- No automatic rejection, outreach, representation, or client submission is performed.

**Important:** qualification is an evidence-based screening aid, not a hiring decision. Recruiters remain responsible for verifying information and choosing the next step.

## Milestone 5: Candidate Communication (in development)

- Create initial outreach, LinkedIn introduction, follow-up, screening availability, and work authorization/engagement-check drafts.
- Personalize drafts from saved candidate and confirmed job fields.
- Respect candidate contact preference and Do Not Contact flags.
- Require a human approval step before a draft can be marked approved.
- Record manual sending only after the recruiter explicitly confirms they sent the approved message themselves.
- Maintain message status and activity history.
- No email or LinkedIn messages are sent automatically by this milestone.

## Milestone 6: OPT Recruiter Screening (in development)

- Create screening sessions for a candidate and confirmed job requirement.
- Capture candidate-stated work authorization, OPT/STEM OPT dates, sponsorship needs, C2C/W2 preference, experience, location, work arrangement, rate, availability, and interview windows.
- Record a separate confirmation status and evidence note for each answer.
- Capture explicit candidate consent to submit their profile to a specific client/role.
- Apply only candidate-confirmed answers to the candidate profile; unconfirmed answers remain screening notes.
- Track session status, recruiter notes, and activity history.
- Screening is recruiter recordkeeping, not immigration/legal advice. Do not store passport numbers, SSNs, or unnecessary sensitive identifiers.

## Milestone 7: Advanced Matching (in development)

- Produce explainable candidate-to-job scores with criterion-level weights and evidence.
- Compare mandatory and preferred skills, experience, location, candidate-confirmed work authorization, candidate-confirmed engagement type, and candidate-reported availability.
- Normalize selected common technology skill variants.
- Show score bands and missing/unknown evidence; insufficient job criteria produce an insufficient-data result rather than a misleading score.
- Store matching runs and recruiter decisions/notes.
- Matching is advisory only. It does not automatically reject candidates, contact candidates, or submit profiles.

**Important:** this version uses deterministic, explainable rules; it is not a connected LLM and does not guarantee candidate suitability.

## Milestone 8: Client Submission Management (in development)

- Maintain client company and contact records.
- Create a submission draft only after the job is confirmed, candidate screening is completed, explicit candidate consent is Yes for that role, and the recruiter qualification decision is “Proceed to Client Submission”.
- Require a separate internal approval before a submission can be marked manually submitted.
- Record client feedback, status changes, withdrawals, and activity history.
- Prevent duplicate active submissions for the same candidate, client, and job.
- Recru Agent does not email or transmit candidate profiles to clients automatically.

## Milestone 9: Interview Management

- Schedule interview rounds only after a client has requested an interview for a manually submitted profile.
- Track round, date/time, time zone, format, meeting link/location, interviewer names, and candidate confirmation.
- Validate future date/time values against an explicit IANA time zone and prevent duplicate active round numbers for the same submission.
- Support rescheduling, completion through recorded feedback, cancellation, and no-show statuses; closed interviews cannot be reopened.
- Record candidate confirmation, interviewer feedback, and outcomes (Strong Hire, Hire, No Hire, Maybe, Additional Round).
- Maintain interview activity history.
- Calendar invitations and participant notifications remain manual; no external calendar or email is sent automatically.

## Milestone 10: Recruitment Pipeline

- Maintain one candidate-to-job pipeline record with stage tracking from Sourcing, Qualification, Screening, Client Submission, Interview, and Offer through Placed, Rejected, or Withdrawn.
- Provide recruiter-facing pipeline workspace with stage/status filters and candidate/job search.
- Track recruiter owner, next action, due date/time, and notes.
- Record stage changes and recruiter activities in a timestamped history.
- Prevent duplicate candidate/job pipeline records, backward stage movement, and reopening terminal outcomes.
- Automatically create or advance pipeline records from existing sourcing, qualification, screening, submission, and interview workflows where supported.
- Pipeline updates do not send messages, submit profiles, or make hiring decisions automatically.

## Milestone 11: Recruiter Productivity Dashboard

- Provide selectable 7-, 30-, 90-, and 365-day reporting periods.
- Summarize new requirements, candidate records, sourcing tasks, pending approvals, active pipeline, completed screenings, client submissions, and interviews.
- Show pipeline distribution by stage, recruiter workload, qualification decisions, submission statuses, sourcing progress, and recent workflow activity.
- Highlight overdue and upcoming pipeline actions only when a time-zone offset is available; local due times without an offset are not falsely classified.
- Dashboard metrics are descriptive workflow counts, not recruiter performance scores or candidate suitability decisions.

## Milestone 12: Security, Quality and Release

- Require authenticated sessions for application APIs; sign-in is bootstrapped from deployment secrets rather than a hard-coded default account.
- Store passwords as salted PBKDF2-HMAC-SHA256 hashes, use random opaque sessions, HttpOnly/SameSite cookies, an 8-hour session expiry, and sign-in rate limiting.
- Support Admin, Recruiter, and Reviewer roles. Reviewers can update only approval and qualification records; administrators manage users and view the audit log.
- Record authenticated write actions in an audit log without copying request bodies or candidate content.
- Provide administrator-controlled user management, password changes, privacy request tracking, candidate erasure, and explicit retention previews/purges.
- Add security response headers and disable public interactive API documentation.
- Render Blueprint requests ADMIN_USERNAME, ADMIN_PASSWORD, and SESSION_SECRET as private environment values. Never commit credentials or session secrets.
- **Release limitation:** this codebase still uses SQLite and local file storage. It does not yet provide multi-tenant row isolation, managed persistent database/storage, encryption at rest, automated backups, or complete privacy/retention/deletion workflows. These infrastructure and governance controls must be completed before real candidate data or external recruiter rollout.
- Formal runtime verification, security review, recovery testing, and release sign-off remain deferred until all milestone development is complete.

### Authentication setup

Configure these environment variables before using the application:
- `ADMIN_USERNAME`: initial administrator username.
- `ADMIN_PASSWORD`: initial administrator password (at least 12 characters).
- `SESSION_SECRET`: a long random secret used to protect session tokens.
- `AUTH_COOKIE_SECURE=true` on HTTPS hosting; use false only for local HTTP development.

The initial administrator is created once when the application starts with these values. ADMIN_PASSWORD must be at least 12 characters and SESSION_SECRET at least 32 characters. Later password changes should be made from the in-app Account Security section. If credentials are missing or too weak, the application intentionally blocks API access and shows an administrator-configuration message.

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

Application-level login, role-based access, audit logging, and admin privacy/retention workflows are implemented. However, there is no multi-tenant row isolation, managed persistent database/file storage, verified encryption at rest, automated backup/restore, or external security assessment. Use fictional data only until the release gates in SECURITY_RELEASE_CHECKLIST.md are completed. Matching is advisory only; recruiters must verify candidate statements and approve every next step.

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

Milestone 1 development implementation is complete; its runtime verification and test/sign-off remain deferred. Milestone 2 development implementation is complete; runtime verification and testing remain deferred. Milestone 3 development implementation is complete; runtime verification and testing remain deferred. Milestone 4 development implementation is complete; runtime verification and testing remain deferred. Milestone 5 development implementation is complete; runtime verification and testing remain deferred. Milestone 6 development implementation is complete; runtime verification and testing remain deferred. Milestone 7 development implementation is complete; runtime verification and testing remain deferred. Milestone 8 development implementation is complete; runtime verification and testing remain deferred. Milestone 9 development implementation is complete; runtime verification and testing remain deferred.

Milestone 10 development implementation is complete; runtime verification and testing remain deferred.

Milestone 11 development implementation is complete; runtime verification and testing remain deferred.

Milestone 12 application-level security and privacy implementation is complete; persistent storage, deployment hardening, formal security review, milestone testing, and release sign-off remain required. See SECURITY_RELEASE_CHECKLIST.md.
