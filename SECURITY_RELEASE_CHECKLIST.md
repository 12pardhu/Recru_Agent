# Recru Agent — Security and Release Gate

This checklist is intentionally separate from the deferred milestone test suite. Do not use real candidate data or invite external recruiters until every applicable release gate is reviewed and approved.

## Application controls implemented on the development branch

- [x] Authenticated API sessions with 8-hour expiry.
- [x] Salted PBKDF2-HMAC-SHA256 password storage.
- [x] Initial administrator bootstrapped from deployment secrets; no default password.
- [x] Sign-in rate limiting.
- [x] Admin, Recruiter, and Reviewer roles.
- [x] Reviewer write access limited to approvals and qualification reviews.
- [x] Administrator user management and password change.
- [x] Audit log for authenticated write requests; request bodies are not recorded.
- [x] Security response headers; public API docs disabled.
- [x] Admin privacy request queue, candidate erasure, retention preview, and explicit retention purge.
- [x] Original resume file removal during candidate erasure.
- [x] Secrets are declared as private Render environment values, not committed to source.

## Required before production use

- [ ] Configure ADMIN_USERNAME, ADMIN_PASSWORD (12+ characters), and SESSION_SECRET (32+ characters) in Render's private environment settings.
- [ ] Confirm HTTPS and secure cookie behavior.
- [ ] Choose and configure persistent managed database and document storage. The current SQLite/local-file configuration may be ephemeral on Render Free.
- [ ] Confirm encryption at rest and in transit for the selected database and file storage.
- [ ] Configure automated backups and prove a restore procedure.
- [ ] Decide deployment boundary: dedicate one Recru Agent deployment to one staffing organization until tenant-level data isolation is implemented and reviewed.
- [ ] Approve a written retention schedule and privacy request handling process.
- [ ] Review candidate erasure scope with the organization's privacy/legal owner.
- [ ] Confirm who may be Admin, Recruiter, and Reviewer; enforce least privilege.
- [ ] Review logging, incident response, account offboarding, and secret rotation procedures.
- [ ] Complete the full milestone test suite, security review, backup/restore exercise, and release sign-off.

## Important limitations

The application-level controls do not by themselves make the product production-ready. There is no multi-tenant row isolation, managed persistent database, verified encryption-at-rest configuration, automated backup/restore workflow, or external security assessment in this branch. Privacy erasure removes the candidate and linked workflow records handled by the application; the organization must also manage exported files, email copies, external systems, backups, and any legal retention obligations.

## Deployment rule

Keep this branch separate from main and do not deploy it to the live Render service until the user explicitly approves the release and all required secrets and storage decisions are ready.
