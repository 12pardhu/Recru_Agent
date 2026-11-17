# Pilot safety, privacy and sourcing boundaries

## Authentication and access
- This build includes application-level login, session cookies, recruiter/reviewer/admin roles, and request auditing. Verify role restrictions and session behavior using the pilot test suite; smoke CI is not a security audit.
- Configure a strong unique `ADMIN_USERNAME`, `ADMIN_PASSWORD` (at least 12 characters), and `SESSION_SECRET` (at least 32 characters) in Render's environment settings. Never commit or share these values.
- Use HTTPS only. The app sets secure session cookies on Render.
- Do not share pilot accounts. Deactivate accounts when a tester leaves.

## Beta data restriction — important
- The existing Render Free service uses SQLite and local filesystem storage. Filesystem contents may be lost during restart, redeploy, replacement or instance changes. No reliable production backup/restore has been established.
- Use fictional names, synthetic resumes, reserved example email addresses and fake client/vendor records only.
- Do not enter real candidate personal data, real phone numbers, real email addresses, real resumes, EAD/immigration records, passport numbers, SSNs, or confidential client/vendor information.
- Do not rely on the app as a system of record. Treat test data as disposable.
- Do not invite external testers until the admin has confirmed authentication is active, created separate accounts, and verified that the deployed build matches the test-suite commit.

## Sourcing and recruiter decisions
- This prototype does not connect to a LinkedIn API and does not scrape, crawl, bulk-extract, or bypass LinkedIn controls.
- It prepares platform search plans/links. A recruiter must use their authorized platform account, inspect results, and manually record information they are permitted to use.
- Open to Work is a visible profile signal, not proof of immediate availability or interest in a specific role. Record observed evidence and date; do not infer it.
- Work authorization, OPT/STEM OPT dates, and C2C/W2 preference must be directly confirmed with the candidate. Unknown remains Unknown.
- Matching scores are shortlist aids, not hiring decisions. Human review is required before outreach, representation, or submission.
- Candidate consent is job/client specific. RTR is tracked separately for the relevant job. Do not reuse consent or RTR across clients/roles.
- Outreach, offers, interview invitations and client submissions remain manual recruiter actions. No automatic messaging or transmission is performed.

## Production blockers
Before operational use with real records, complete and independently verify:
- Durable managed database and persistent file/object storage, with tested backups and restore.
- Tenant isolation and authorization checks across every endpoint and file download.
- Encryption and secret management, audit-log protection, retention/deletion and privacy request handling.
- Malware scanning and file validation for uploads.
- Security review, dependency review, monitoring, incident response and recovery plan.
- Full functional/browser/end-to-end regression tests and recruiter sign-off.
- Legal/privacy review for the intended jurisdictions and staffing workflow.

This document is a beta safety boundary, not legal advice or a security certification.
