# Safe-use and workflow boundaries

- This app is a recruiter-assist prototype, not an autonomous recruiting or employment decision system.
- LinkedIn sourcing is intentionally human-assisted. Use LinkedIn through permitted normal user workflows and follow LinkedIn's terms; no scraping, session extraction, or prohibited automation is included.
- Never infer OPT/STEM OPT, work authorization, or C2C availability from a profile. Store `Unknown` until the candidate confirms.
- Matching scores are transparent shortlist aids only. A recruiter must review evidence and make decisions.
- Human approval is required before outreach, representation, or submission. This prototype does not send messages or submit candidates.
- Resume upload is not implemented in this starter build; the candidate form supports manually entered recruiter notes/resume text.
- Before production: implement authentication (OIDC/JWT), role-based access control, tenant isolation, TLS, secure secrets, audit protection, malware scanning, retention/deletion controls, backups, privacy/legal review, and managed persistent storage.
- Do not enter sensitive personal data into an unauthenticated deployment.
