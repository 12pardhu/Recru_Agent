# Safety, privacy and sourcing boundaries

- This prototype does not connect to a LinkedIn API and does not scrape, crawl, bulk-extract, or bypass LinkedIn controls.
- It prepares a People-search URL. A recruiter must use their authorized LinkedIn account, inspect results, and manually record information they are permitted to use.
- Open to Work is a visible profile signal, not proof of immediate availability or interest in a specific role. Record the observed evidence and date; do not infer it.
- Work authorization and C2C must be directly confirmed with the candidate. Unknown remains Unknown.
- Matching scores are shortlist aids, not hiring decisions. Human review is required before outreach, representation, or submission.
- No authentication or access control exists. Do not put real candidate personal data or resumes into this deployment.
- Before production add OIDC/JWT authentication, RBAC, tenant isolation, HTTPS enforcement, managed PostgreSQL with backups, secrets management, audit protection, malware scanning, data retention/deletion, privacy/legal review and monitoring.