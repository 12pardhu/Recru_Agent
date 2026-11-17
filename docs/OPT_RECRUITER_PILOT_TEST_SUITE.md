# Recru Agent — OPT Recruiter Pilot Test Suite

**Purpose:** Have working OPT recruiters validate the end-to-end human staffing workflow and report product gaps before wider use.

**Build under test:** Development branch `feature/multi-platform-sourcing` (see the linked pull request and deployment announcement for the exact commit).

**Important pilot boundary:** This is a beta test, not a production system. The current Render Free deployment uses local SQLite/filesystem storage that may be lost on restart, redeploy, or instance replacement. Use fictional names, fictional contact details, synthetic resumes, and test companies only. Do not upload real candidate resumes, EAD documents, passports, SSNs, immigration records, client confidential data, or real contact details. Do not rely on the app as the system of record.

## 1. How fellow recruiters should test

1. Sign in using the pilot account provided by the administrator. Do not share accounts.
2. Use only the fictional sample data supplied for the pilot.
3. Work through the cases in order where practical. Some later cases depend on earlier records.
4. For each case, record **PASS**, **FAIL**, **BLOCKED**, or **NOT TESTED**. A case is PASS only when the observed result matches the expected result.
5. For every failure, capture the case ID, screen/URL, steps, expected result, actual result, browser/device, timestamp and severity. Use synthetic data in screenshots.
6. Do not send real messages, submit real candidate profiles, or contact real clients/vendors from the test environment.

## 2. Severity definitions

| Severity | Meaning | Example |
|---|---|---|
| Critical | Security/privacy exposure, unauthorized access, data loss, or incorrect submission that could cause serious harm | Recruiter can see another tenant's records; unconsented candidate is submitted |
| High | Core workflow is blocked or important information is materially wrong | Cannot save a requirement; signed RTR not enforced |
| Medium | Feature works incorrectly but a safe workaround exists | Follow-up filter gives wrong count |
| Low | Cosmetic, wording, layout, or minor usability issue | Misaligned label |

## 3. Fictional pilot data

Use these invented records consistently:

- **Client:** Northstar Demo Systems LLC
- **Vendor:** Bluebird Demo Staffing LLC
- **End client:** Contoso Sample Finance
- **Requirement A:** Java Developer; 4+ years; Java, Spring Boot, Microservices; Dallas, TX or Austin, TX; hybrid; C2C considered only when candidate confirms; OPT/STEM OPT considered subject to client confirmation.
- **Requirement B:** Python Developer; 5+ years; Python, FastAPI, AWS; Houston, TX; remote; W2.
- **Candidate A:** Alex Sample; 5 years total, 4 years Java/Spring Boot; Dallas; fictional OPT dates; C2C preference explicitly confirmed; synthetic resume.
- **Candidate B:** Jordan Example; 6 years total, 3 years Python; Houston; work authorization unknown; W2 preference not yet confirmed.
- **Candidate C:** Taylor Demo; 2 years Java; Austin; synthetic resume; no work authorization answer.
- **Candidate D:** Casey Fiction; 7 years Python/FastAPI/AWS; Houston; candidate-confirmed W2; synthetic resume.
- Use reserved example addresses such as `alex.sample@example.com`, `jordan.example@example.com`, and phone numbers that are clearly fictional/non-routable in your local test notes. Never use a real person's details.

## 4. Test cases

### A. Login, access and session safety

| ID | Test | Steps | Expected result | Result / notes |
|---|---|---|---|---|
| AUTH-01 | Valid login | Sign in with pilot credentials | Dashboard opens; session established | |
| AUTH-02 | Invalid password | Enter correct username and wrong password | Login rejected with safe error; no session | |
| AUTH-03 | Empty credentials | Submit blank fields | Required-field validation appears | |
| AUTH-04 | Unauthenticated API | Sign out, then open a protected API route | Request is rejected with 401 | |
| AUTH-05 | Logout | Sign out and revisit dashboard/protected API | Session is invalidated; protected API requires login | |
| AUTH-06 | Session expiry | Use an expired test session if available | User is asked to sign in again | |
| AUTH-07 | Recruiter role | Sign in as recruiter | Recruiter can perform permitted workflow actions | |
| AUTH-08 | Reviewer restrictions | Sign in as reviewer and attempt a write action | Restricted write is denied; permitted review actions work | |
| AUTH-09 | Admin user management | Admin creates/deactivates a test user | New user can sign in; deactivated user cannot | |
| AUTH-10 | Password change | Change password and sign in again | New password works; old password fails | |

### B. Requirement intake and approval

| ID | Test | Steps | Expected result | Result / notes |
|---|---|---|---|---|
| REQ-01 | Client requirement intake | Create Requirement A from a client | Record saves with client relationship and source details | |
| REQ-02 | Vendor requirement intake | Create Requirement B from a vendor; set end client | Vendor and end-client relationships remain distinguishable | |
| REQ-03 | All intake channels | Repeat intake using Email, WhatsApp, Phone and LinkedIn | Each channel is stored accurately | |
| REQ-04 | Required fields | Try saving without job title or required fields | Validation explains what is missing | |
| REQ-05 | JD content | Paste/upload a synthetic JD | Original text/file is associated with the draft | |
| REQ-06 | Requirement extraction | Review extracted title, skills, experience, locations and work arrangement | Extracted values are visible with evidence; unknowns are not invented | |
| REQ-07 | Conflicting criteria | Enter contradictory experience/location/rate details | Conflict or missing-information warnings appear | |
| REQ-08 | Clarification notes | Add client/vendor clarification and update fields | Notes and revised values are retained | |
| REQ-09 | Duplicate requirement | Enter the same client/vendor job twice | Duplicate warning appears; recruiter can inspect before proceeding | |
| REQ-10 | Approval gate | Attempt sourcing before recruiter approval/confirmation | Sourcing is blocked until requirement is confirmed/ready | |
| REQ-11 | Revision history | Revise a confirmed requirement | New version is created; earlier version remains inspectable | |
| REQ-12 | Requirement list | Filter/search requirements by status, client/vendor and title | Correct records and statuses are shown | |

### C. Sourcing across four platforms

| ID | Test | Steps | Expected result | Result / notes |
|---|---|---|---|---|
| SRC-01 | LinkedIn search plan | Prepare sourcing for Requirement A | Relevant query variants and locations appear | |
| SRC-02 | Dice search plan | Select Dice and prepare search | Dice search plan/link is generated | |
| SRC-03 | Indeed search plan | Select Indeed and prepare search | Indeed search plan/link is generated | |
| SRC-04 | Monster search plan | Select Monster and prepare search | Monster search plan/link is generated | |
| SRC-05 | Location-specific search | Use Dallas and Austin for Requirement A | Search variants respect the requirement's locations | |
| SRC-06 | Daily target | Set target between 50 and 100 | Target is saved and displayed for the sourcing task | |
| SRC-07 | Search progress | Mark a search In Progress, Completed and Skipped | Status and activity update correctly | |
| SRC-08 | Open external search | Open a generated platform link | Correct external platform/search opens; app does not scrape | |
| SRC-09 | Manual candidate capture | Add Alex Sample with source platform, profile URL and evidence | Candidate is saved with source provenance | |
| SRC-10 | Duplicate candidate | Add Alex again using same email/profile URL | Duplicate warning/prevention works | |
| SRC-11 | Open to Work | Record Open to Work as observed signal with date/evidence | Signal is recorded separately; it is not treated as confirmed availability | |
| SRC-12 | Unknown work authorization | Leave authorization unknown | System preserves Unknown; it does not infer OPT/STEM OPT | |

### D. Resume and candidate profile

| ID | Test | Steps | Expected result | Result / notes |
|---|---|---|---|---|
| RES-01 | Synthetic PDF resume | Upload synthetic PDF | Text is extracted where supported; recruiter can review | |
| RES-02 | Synthetic DOCX resume | Upload synthetic DOCX | Text is extracted and editable for review | |
| RES-03 | Unsupported file | Upload unsupported file type | Clear validation error; no corrupt candidate record | |
| RES-04 | Oversized file | Upload file above configured limit | Upload is rejected with clear message | |
| RES-05 | Complex/scanned resume | Upload a synthetic scanned/column resume | Missing extraction is visible; no false certainty; manual correction possible | |
| RES-06 | Review before save | Edit extracted name, skills and experience | Recruiter edits are saved; raw extraction is not silently trusted | |
| RES-07 | Candidate profile | Open saved candidate | Contact/source/profile/resume fields display consistently | |
| RES-08 | Resume replacement | Attach a revised synthetic resume | Current attachment is clear; history/behavior is understandable | |

### E. Qualification and matching

| ID | Test | Steps | Expected result | Result / notes |
|---|---|---|---|---|
| QUAL-01 | Strong match | Compare Alex with Requirement A | Relevant skills/experience/location evidence is shown | |
| QUAL-02 | Experience shortfall | Compare Taylor with Requirement A | Experience gap is visible; no unsupported claims | |
| QUAL-03 | Missing skill evidence | Candidate resume does not mention a mandatory skill | Status is Unknown/Needs Review, not automatically “does not have skill” | |
| QUAL-04 | Location mismatch | Compare a candidate outside required locations | Location mismatch is explicit | |
| QUAL-05 | Authorization unknown | Candidate has not confirmed OPT/STEM OPT | Authorization remains Unknown and is not inferred | |
| QUAL-06 | C2C unknown | Candidate has not confirmed C2C | C2C remains Unknown | |
| QUAL-07 | Evidence traceability | Open a qualification result | Criteria, source evidence and recruiter decision are visible | |
| QUAL-08 | Human decision | Choose Proceed, Hold, Not a Fit or Needs More Information | Decision and notes are recorded; no automatic rejection/outreach | |
| QUAL-09 | Insufficient JD | Match against incomplete requirement | System indicates insufficient data instead of misleading score | |
| QUAL-10 | Re-run after edit | Update candidate evidence and rerun qualification | New result reflects updated evidence and is distinguishable from prior run | |

### F. Candidate communication and contact history

| ID | Test | Steps | Expected result | Result / notes |
|---|---|---|---|---|
| COM-01 | LinkedIn draft | Create LinkedIn outreach draft | Draft uses relevant candidate/job fields and can be edited | |
| COM-02 | Email draft | Create email outreach draft | Subject/body are editable; nothing is sent automatically | |
| COM-03 | Phone activity | Record a call attempt and outcome | Channel, direction, time, outcome and notes are stored | |
| COM-04 | WhatsApp activity | Record a WhatsApp contact attempt | Interaction is logged; no automatic message is sent | |
| COM-05 | Candidate response | Record interested, not interested, no response and callback outcomes | Correct status and notes are retained | |
| COM-06 | Do Not Contact | Set Do Not Contact and attempt to prepare outreach | Contact guard is enforced and visible | |
| COM-07 | Manual send confirmation | Mark a draft sent without confirming manual send | System prevents misleading sent status | |
| COM-08 | Contact history | View candidate communication history | Chronological interactions are visible and linked to the right job | |

### G. OPT screening, consent and RTR

| ID | Test | Steps | Expected result | Result / notes |
|---|---|---|---|---|
| SCR-01 | Create screening | Start a screening session for Alex and Requirement A | Session is linked to correct candidate and job | |
| SCR-02 | Total/relevant experience | Enter both values separately | Both values are stored and shown distinctly | |
| SCR-03 | Current project | Record current project and technical responsibilities | Candidate-stated details are retained | |
| SCR-04 | OPT details | Record candidate-confirmed OPT status and dates | Confirmation and evidence/date are visible | |
| SCR-05 | STEM OPT details | Record candidate-confirmed STEM OPT and validity | Dates and confirmation are retained; no immigration advice is implied | |
| SCR-06 | C2C/W2 confirmation | Record explicit candidate answer | Engagement preference is marked confirmed only when candidate says so | |
| SCR-07 | Rate and availability | Record expected rate, notice and availability | Values are saved with the correct candidate/job | |
| SCR-08 | Unknown answers | Leave selected answers unanswered | Unknown stays Unknown; system does not auto-fill | |
| SCR-09 | Job-specific consent | Record consent for Requirement A | Consent is linked to that specific job/client | |
| SCR-10 | Consent missing | Attempt to progress to submission without consent | Submission readiness is blocked | |
| SCR-11 | Consent for different job | Give consent for A, then attempt submission to B | Consent for A is not reused for B | |
| SCR-12 | RTR requested | Create an RTR requirement for the job/client | RTR request is linked to this screening/job | |
| SCR-13 | RTR unsigned | Attempt submission while RTR is required but not signed | Submission is blocked | |
| SCR-14 | RTR signed | Record signed status and evidence reference | Signed status and evidence reference are visible | |
| SCR-15 | RTR expired | Set expiry in the past and attempt submission | Submission is blocked | |
| SCR-16 | RTR not required | Mark RTR not required for the specific job, where policy allows | Requirement is explicit; no false signed status is created | |
| SCR-17 | Screening completion | Complete screening with required answers/consent | Completion is recorded; unresolved gates remain visible | |

### H. Client submission and duplicate protection

| ID | Test | Steps | Expected result | Result / notes |
|---|---|---|---|---|
| SUB-01 | Create submission draft | Use qualified candidate, completed screening and job consent | Draft is created for the intended client/job | |
| SUB-02 | Missing consent | Try draft/approval without job-specific consent | Blocked with clear reason | |
| SUB-03 | Missing RTR | Require RTR but leave unsigned | Submission cannot be approved/marked submitted | |
| SUB-04 | Missing rate confirmation | Leave candidate rate unconfirmed | Readiness warning/block is shown as configured | |
| SUB-05 | Approval workflow | Submit draft for internal approval | Authorized approver can approve/reject; action is audited | |
| SUB-06 | Manual submission | Mark as manually submitted after actual test-only action | Status changes only after recruiter confirmation | |
| SUB-07 | Duplicate same client/job | Submit same candidate to same client/job twice | Duplicate active submission is blocked or warned | |
| SUB-08 | Multiple vendors same end client | Attempt duplicate route through two vendors to same end client | Duplicate risk is visible; recruiter can distinguish client/end-client path | |
| SUB-09 | Client feedback | Record interview requested, rejected, hold, more info and offer outcomes | Feedback is saved against correct submission | |
| SUB-10 | Withdraw submission | Withdraw a test submission | Status/history reflect withdrawal; no external message is sent | |

### I. Interview management

| ID | Test | Steps | Expected result | Result / notes |
|---|---|---|---|---|
| INT-01 | Schedule interview | Schedule only after client interview request | Interview record is created against the correct submission | |
| INT-02 | Time zone | Set interview date/time and IANA time zone | Display and stored time are consistent | |
| INT-03 | Past date | Attempt to schedule in the past | Validation rejects or clearly warns | |
| INT-04 | Duplicate round | Add same active round number twice for same submission | Duplicate active round is prevented | |
| INT-05 | Reschedule | Change date/time and reason | Updated schedule and history are visible | |
| INT-06 | Candidate confirmation | Record confirmed/not confirmed | Candidate confirmation status is clear | |
| INT-07 | Interview feedback | Record interviewer outcome and notes | Feedback is saved and linked to the correct round | |
| INT-08 | Cancel/no-show | Mark cancelled or no-show | Status and history update correctly | |

### J. Offer, placement, joining and onboarding

| ID | Test | Steps | Expected result | Result / notes |
|---|---|---|---|---|
| OFF-01 | Offer gate | Try creating offer without client feedback = Offer | Offer creation is blocked | |
| OFF-02 | Create offer | Record contract/C2C/W2/full-time type, rate and dates | Offer is linked to correct submission/candidate/client | |
| OFF-03 | Duplicate offer | Create second offer for same submission | Duplicate is blocked | |
| OFF-04 | Candidate acceptance | Mark Accepted after recruiter confirms candidate response | Acceptance and activity history are recorded | |
| OFF-05 | Candidate decline | Mark Declined | Decline is recorded without marking placement | |
| OFF-06 | Joining before acceptance | Try setting Joined while offer not accepted | System blocks the transition | |
| OFF-07 | Onboarding checklist | Complete the required checklist | Completion states are retained | |
| OFF-08 | Incomplete onboarding | Try marking Joined with unchecked tasks | System blocks joining and identifies incomplete tasks | |
| OFF-09 | Confirm joining | Mark Accepted offer Joined with checklist complete and date | Pipeline moves to Placed; join date is saved | |
| OFF-10 | Did Not Join | Record candidate did not join | Status is visible; pipeline does not falsely show successful placement | |
| OFF-11 | Post-placement follow-up | Create follow-up after joining | Reminder appears in follow-up queue | |

### K. Follow-up center and dashboard

| ID | Test | Steps | Expected result | Result / notes |
|---|---|---|---|---|
| FUP-01 | Requirement reminder | Create clarification reminder | Reminder appears in queue | |
| FUP-02 | Candidate reminder | Create candidate callback reminder | Candidate and optional job link display correctly | |
| FUP-03 | Vendor/client reminder | Create vendor or client follow-up | Related party and reminder type display correctly | |
| FUP-04 | Submission/interview reminder | Create a due reminder | Correct reminder appears in the central queue | |
| FUP-05 | Priority | Set High/Urgent | Priority is visible and count updates | |
| FUP-06 | Due filter | Create past-due and future reminders; filter due/overdue | Only due/incomplete reminders appear | |
| FUP-07 | Status update | Move Open → In Progress → Completed | Status and completion timestamp update | |
| FUP-08 | Cancel reminder | Mark reminder Cancelled | It is no longer counted as open | |
| FUP-09 | Edit reminder | Change due date, owner and notes | Updated values persist after refresh | |
| FUP-10 | Dashboard consistency | Compare dashboard totals with underlying test records | Counts are consistent or differences are explained | |

### L. Privacy, reliability and usability

| ID | Test | Steps | Expected result | Result / notes |
|---|---|---|---|---|
| SAFE-01 | No scraping | Use platform search links | App opens search only; does not scrape or bulk-import profiles | |
| SAFE-02 | No auto outreach | Prepare candidate message | Message remains a draft until manually sent outside app | |
| SAFE-03 | No auto submission | Prepare client submission | App records recruiter-confirmed manual action; no profile is transmitted | |
| SAFE-04 | Unknown data | Leave work authorization/C2C unknown | No inferred confirmation or auto-match claim | |
| SAFE-05 | Browser refresh | Refresh page after saving a test record | Record remains visible in current test instance | |
| SAFE-06 | Session timeout | Leave session idle beyond configured expiry in a controlled test | Re-authentication is required | |
| SAFE-07 | Responsive layout | Test common desktop and mobile widths | Critical controls remain usable; no hidden action buttons | |
| SAFE-08 | Error handling | Submit invalid values or simulate unavailable route | User receives understandable error; app does not silently claim success | |
| SAFE-09 | Data export | Export test records where feature is available | Export is readable and matches selected test data | |
| SAFE-10 | Persistence warning | Restart/redeploy behavior is assessed only by administrator | Pilot testers understand local data may be lost; no real records are used | |

## 5. Pilot completion criteria

Do not call the product ready for operational candidate data until:

- All Critical and High defects are fixed and retested.
- All required end-to-end cases pass on the deployed build.
- Login, role restrictions, logout and session expiry are verified.
- Consent, RTR and duplicate-submission guards are verified.
- Recruiters confirm the requirement → sourcing → screening → submission → interview → offer → joining workflow is usable.
- Persistence, backup/restore, tenant isolation, privacy deletion, monitoring and security review are separately completed before production use.

A green GitHub smoke check only confirms Python compilation, application import and route registration. It does **not** mean all test cases passed.

## 6. Tester result format

For each test, record:

- Tester code (do not write personal details)
- Test case ID
- Result: PASS / FAIL / BLOCKED / NOT TESTED
- Actual result
- Severity if failed
- Screenshot reference (synthetic data only)
- Browser/device
- Date/time
- Suggested improvement

## 7. Feedback questions for OPT recruiters

1. Which step in your real daily workflow is missing?
2. Which fields do you collect from a client/vendor before accepting a requirement?
3. Which candidate screening questions are missing or redundant?
4. What causes duplicate submissions in your current process?
5. What would make the sourcing workflow faster without violating platform rules?
6. Which reminders should be automatic alerts versus manual tasks?
7. Which page or action is confusing or takes too many clicks?
8. What would stop you from using this product daily?
9. What must be fixed before you trust it with real candidate records?
10. What is the single most valuable improvement for the next release?

**Feedback rule:** Report workflow/product defects, not real candidate information. Use fictional examples only.
