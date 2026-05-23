"""Per-department knowledge base text injected into each agent's system prompt.

In a real system these would be RAG'd from documents. For the demo we keep
them inline so each department has a distinct, scoped policy book.
"""
from __future__ import annotations

REGISTRAR_KB = """\
OFFICE OF THE REGISTRAR — POLICY HIGHLIGHTS
- A student cannot enroll in a course if ANY active hold exists on the account
  (financial, advising, library, immunization, etc.). Holds must be cleared by
  the originating department first.
- Prerequisites must be completed with a grade of C or better to satisfy the
  requirement. A D, F, or W in a prerequisite does NOT satisfy it.
- Add/drop deadline: end of week 2 of the term. After week 2, a withdrawal
  shows as W on the transcript.
- Registration appointments open by class standing: seniors first, then
  juniors, sophomores, freshmen.
- Official transcripts can be requested from the Registrar portal. Unofficial
  transcripts are visible immediately in the student dashboard.
- Drop = before deadline, no W. Withdrawal = after deadline, shows W.
"""

ADVISING_KB = """\
ACADEMIC ADVISING — POLICY HIGHLIGHTS
- All students must meet with an advisor before registering for the term in
  which they intend to graduate, and as required by any active advising hold.
- Degree progress is computed against the student's declared major. Required
  courses are grouped into: major, ge (general education), and elective.
- A course is considered "completed" only with a passing grade (C or better).
- Students with GPA below 2.0 are placed on academic probation and must meet
  with an advisor before continuing.
- Capstone (CS450) must be taken in the final term and requires CS301.
"""

FINANCIAL_KB = """\
FINANCIAL AID & BURSAR — POLICY HIGHLIGHTS
- An unpaid balance past its due date creates a financial hold on the account
  which blocks registration, transcript requests, and graduation.
- Payment plans are available — contact the Bursar to set one up; this clears
  the financial hold once the first installment is paid.
- Scholarships are applied against tuition at the start of each term.
- FAFSA must be renewed each academic year for federal aid to continue.
- Refunds for dropped courses follow the published refund schedule (100%
  before week 2, 50% weeks 3-4, 0% after week 4).
"""

IT_KB = """\
IT HELP DESK — POLICY HIGHLIGHTS
- After 5 failed login attempts the SSO account auto-locks. The student must
  contact the help desk for a password reset OR wait 24 hours for auto-unlock.
- Email quota is 15 GB. At 90% usage the system warns; at 100% sending is
  blocked but receiving still works. Recommend archiving old attachments.
- Campus Wi-Fi requires SSO; if SSO is locked, Wi-Fi will also fail to
  authenticate.
- Password resets can be self-served from id.mock-university.edu when the
  account is not locked.
"""

HOUSING_KB = """\
HOUSING & DINING — POLICY HIGHLIGHTS
- Housing assignments are made annually. Students without a housing record
  have not been assigned and should apply through the Housing portal.
- Meal plan tiers: Unlimited, Block 160 (160 meals/term), Block 80.
- Dining dollars roll over between fall and spring but expire at year end.
- Room changes require submitting a room change request through Housing
  Services; off-cycle changes are reviewed weekly.
"""

KB_BY_CODE = {
    "REGISTRAR": REGISTRAR_KB,
    "ADVISING": ADVISING_KB,
    "FINANCIAL": FINANCIAL_KB,
    "IT": IT_KB,
    "HOUSING": HOUSING_KB,
}
