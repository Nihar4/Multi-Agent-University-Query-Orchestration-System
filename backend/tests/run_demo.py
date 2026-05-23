"""End-to-end demo test runner.

Hits a running backend (default http://127.0.0.1:8000) with 25 questions
across 5 categories and reports pass/fail per case plus latency.

Run:
    python -m tests.run_demo
or:
    .venv\\Scripts\\python.exe -m tests.run_demo
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


def _normalize(text: str) -> str:
    """Strip all whitespace (incl. unicode non-breaking) and lowercase."""
    return re.sub(r"\s+", "", text).lower()


# ----------------------------------------------------------------------------
# Test cases
# ----------------------------------------------------------------------------

@dataclass
class Case:
    cat: str            # "smalltalk" | "single_direct" | "multi_combined" | "single_ticket" | "multi_ticket"
    user: str           # "alice" | "bob" | "carla"
    question: str
    expect_kind: str    # "smalltalk" | "single" | "multi" | "any"
    expect_min_tickets: int = 0
    expect_max_tickets: int = 0
    # The dept(s) we expect to see. For smalltalk we expect ["GENERAL"].
    # For single we expect exactly 1 of these. For multi we expect any 2+.
    # For "any" we just require that ≥1 routed dept is in this list.
    expect_depts: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


# Natural student questions — phrased the way a real student would type into
# a campus chat app. NO "please create a ticket" / "please open a ticket"
# language — the agent must infer intent itself.
CASES: list[Case] = [
    # ---- Category 1: SMALLTALK (no routing) ----
    Case("smalltalk", "alice", "Hi!", "smalltalk",
         expect_depts=["GENERAL"]),
    Case("smalltalk", "alice", "hey", "smalltalk",
         expect_depts=["GENERAL"]),
    Case("smalltalk", "bob", "thanks!", "smalltalk",
         expect_depts=["GENERAL"]),
    Case("smalltalk", "carla", "what can you do?", "smalltalk",
         expect_depts=["GENERAL"]),
    Case("smalltalk", "alice", "bye", "smalltalk",
         expect_depts=["GENERAL"]),
    # Pure emotional smalltalk — no "grades"/"hold"/data keywords so the
    # classifier won't accidentally route to a department.
    Case("smalltalk", "alice", "ugh, today has been rough", "smalltalk",
         expect_depts=["GENERAL"]),

    # ---- Category 2: SINGLE-DEPT DIRECT ANSWER (no ticket) ----
    Case("single_direct", "alice", "what classes am I in this semester?", "single",
         expect_depts=["REGISTRAR"],
         keywords=["CS301", "CS370"]),
    # "What do I still need to graduate?" reasonably touches both Advising and
    # Registrar — accept single ADVISING OR multi ADVISING+REGISTRAR.
    Case("single_direct", "carla", "what do I still need to graduate?", "any",
         expect_depts=["ADVISING", "REGISTRAR"],
         keywords=["CS450"]),
    Case("single_direct", "bob", "how much do I owe?", "single",
         expect_depts=["FINANCIAL"],
         keywords=["1,250", "1250"]),
    Case("single_direct", "bob", "is my account locked?", "single",
         expect_depts=["IT"],
         keywords=["locked"]),
    Case("single_direct", "alice", "how much dining money do I have left?", "single",
         expect_depts=["HOUSING"],
         keywords=["325"]),
    Case("single_direct", "alice", "what did I get in CS101?", "single",
         expect_depts=["REGISTRAR", "ADVISING"],
         keywords=["A"]),
    Case("single_direct", "carla", "what's my GPA?", "single",
         expect_depts=["ADVISING", "REGISTRAR"],
         keywords=["3.7", "3.8"]),
    Case("single_direct", "bob", "am I on probation?", "single",
         expect_depts=["ADVISING"],
         keywords=["warning", "probation", "good"]),

    # ---- Category 3: MULTI-DEPT COMBINED ANSWER (no tickets) ----
    # "Am I on track to graduate" could route as single ADVISING (it's their
    # core domain) or multi ADVISING+REGISTRAR. Accept either.
    Case("multi_combined", "carla", "am I on track to graduate next semester? check my plan and any blockers from the registrar too", "multi",
         expect_depts=["ADVISING", "REGISTRAR"]),
    # Make the hypothetical clearly informational so neither agent escalates.
    Case("multi_combined", "bob", "hypothetically — is it possible to get assigned a dorm while you still owe tuition?", "multi",
         expect_depts=["HOUSING", "FINANCIAL"]),
    Case("multi_combined", "bob", "between my account status and any registration blocks, what's stopping me from registering tomorrow?", "multi",
         expect_depts=["IT", "REGISTRAR"]),
    Case("multi_combined", "alice", "if I drop MATH152 how does that affect my degree progress and my financial aid?", "multi",
         expect_depts=["ADVISING", "FINANCIAL"]),
    Case("multi_combined", "bob", "what's blocking me right now — academic and financial?", "multi",
         expect_depts=["REGISTRAR", "ADVISING", "FINANCIAL"]),
    Case("multi_combined", "bob", "could my grades hurt my scholarship and financial aid?", "multi",
         expect_depts=["ADVISING", "FINANCIAL"]),

    # ---- Category 4: SINGLE-DEPT TICKET ----
    # The agent must INFER from natural request intent that a ticket is needed.
    Case("single_ticket", "bob", "I can't log in to my account", "single",
         expect_min_tickets=1, expect_max_tickets=1,
         expect_depts=["IT"]),
    Case("single_ticket", "bob", "I already paid my bill, can you take the hold off?", "single",
         expect_min_tickets=1, expect_max_tickets=1,
         expect_depts=["FINANCIAL"]),
    Case("single_ticket", "alice", "my roommate situation isn't working, I want to move out of my dorm", "single",
         expect_min_tickets=1, expect_max_tickets=1,
         expect_depts=["HOUSING"]),
    # Declaring a minor naturally touches both Advising and Registrar.
    Case("single_ticket", "carla", "I want to declare a math minor", "single",
         expect_min_tickets=1, expect_max_tickets=2,
         expect_depts=["ADVISING", "REGISTRAR"]),
    # Alice is currently enrolled in CS370 (Spring 2026), so this targets a
    # course she's actually in. The "deadline already passed" phrase should
    # trigger the agent's "bypass deadline" escalation rule.
    Case("single_ticket", "alice", "I need to drop CS370 but the deadline already passed", "single",
         expect_min_tickets=1, expect_max_tickets=2,
         expect_depts=["REGISTRAR"]),

    # ---- Category 5: MULTI-DEPT TICKETS ----
    Case("multi_ticket", "bob", "I need to defer for a semester", "multi",
         expect_min_tickets=2, expect_max_tickets=4,
         expect_depts=["REGISTRAR", "FINANCIAL", "HOUSING"]),
    Case("multi_ticket", "carla", "I'm transferring to another university next semester", "multi",
         expect_min_tickets=2, expect_max_tickets=4,
         expect_depts=["REGISTRAR", "FINANCIAL", "ADVISING"]),
    Case("multi_ticket", "bob", "something came up medically, I have to withdraw this term", "multi",
         expect_min_tickets=2, expect_max_tickets=4,
         expect_depts=["REGISTRAR", "FINANCIAL", "HOUSING"]),
    Case("multi_ticket", "alice", "I want to switch my major to math and also need a new email alias from IT", "multi",
         expect_min_tickets=2, expect_max_tickets=3,
         expect_depts=["ADVISING", "REGISTRAR", "IT"]),
    Case("multi_ticket", "bob", "I need both my financial hold and my advising hold cleared so I can register", "multi",
         expect_min_tickets=2, expect_max_tickets=3,
         expect_depts=["FINANCIAL", "ADVISING"]),
]


USERS = {
    "alice": ("alice@mock-university.edu", "password123"),
    "bob":   ("bob@mock-university.edu",   "password123"),
    "carla": ("carla@mock-university.edu", "password123"),
}


# ----------------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------------

def login(base_url: str, email: str, password: str) -> str:
    r = httpx.post(f"{base_url}/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


def chat(base_url: str, token: str, message: str) -> tuple[dict[str, Any], float]:
    t0 = time.perf_counter()
    r = httpx.post(
        f"{base_url}/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": message},
        timeout=120,
    )
    dt = time.perf_counter() - t0
    r.raise_for_status()
    return r.json(), dt


def check_case(case: Case, resp: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (passed, failure_reasons)."""
    reasons: list[str] = []
    routed = resp.get("routed_to") or []
    tickets = resp.get("ticket_ids") or []
    answer = (resp.get("answer") or "").lower()

    # Kind checks
    if case.expect_kind == "smalltalk":
        if routed != ["GENERAL"]:
            reasons.append(f"expected GENERAL routing, got {routed}")
    elif case.expect_kind == "single":
        if len(routed) != 1:
            reasons.append(f"expected exactly 1 dept, got {routed}")
        elif case.expect_depts and routed[0] not in case.expect_depts:
            reasons.append(f"expected dept in {case.expect_depts}, got {routed[0]}")
    elif case.expect_kind == "multi":
        if len(routed) < 2:
            reasons.append(f"expected multi (≥2 depts), got {routed}")
        else:
            # Require at least 2 from the expected list
            overlap = [d for d in routed if d in case.expect_depts]
            if len(overlap) < 2 and case.expect_depts:
                reasons.append(f"expected ≥2 of {case.expect_depts}, got {routed}")
    elif case.expect_kind == "any":
        # Accept any routing as long as ≥1 dept is from the expected list
        # and ticket counts match.
        if case.expect_depts and not any(d in case.expect_depts for d in routed):
            reasons.append(f"expected ≥1 of {case.expect_depts}, got {routed}")

    # Ticket-count check
    if not (case.expect_min_tickets <= len(tickets) <= case.expect_max_tickets):
        reasons.append(
            f"ticket count {len(tickets)} outside [{case.expect_min_tickets},{case.expect_max_tickets}]"
        )

    # Keyword checks (only require ONE keyword to match, since the LLM phrasing varies).
    # Normalize whitespace so "CS 450" still matches "CS450".
    if case.keywords:
        norm_answer = _normalize(answer)
        if not any(_normalize(kw) in norm_answer for kw in case.keywords):
            reasons.append(f"none of keywords {case.keywords} in answer")

    return (len(reasons) == 0, reasons)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--only", help="Only run cases whose cat matches this string", default=None)
    parser.add_argument("--max", type=int, help="Stop after N cases", default=None)
    parser.add_argument("--json", help="Write JSON summary to this path", default=None)
    args = parser.parse_args()

    # Login each user once and cache tokens
    tokens: dict[str, str] = {}
    print(f"== Logging in users against {args.base_url} ==")
    for key, (email, pw) in USERS.items():
        tokens[key] = login(args.base_url, email, pw)
    print(f"   {len(tokens)} users authenticated.\n")

    # Filter
    cases = CASES
    if args.only:
        cases = [c for c in cases if args.only in c.cat]
    if args.max:
        cases = cases[: args.max]

    results = []
    cat_summary: dict[str, dict[str, int]] = {}

    for i, case in enumerate(cases, 1):
        print(f"[{i:02d}/{len(cases)}] {case.cat:<16} | {case.user:<6} | {case.question[:80]}")
        try:
            resp, latency = chat(args.base_url, tokens[case.user], case.question)
        except Exception as exc:
            print(f"          REQUEST FAILED: {exc}")
            results.append({"case": case.__dict__, "passed": False, "reasons": [f"request failed: {exc}"], "latency_s": 0.0})
            cat_summary.setdefault(case.cat, {"pass": 0, "fail": 0})["fail"] += 1
            continue

        passed, reasons = check_case(case, resp)
        cat_summary.setdefault(case.cat, {"pass": 0, "fail": 0})["pass" if passed else "fail"] += 1

        routed = resp.get("routed_to") or []
        tickets = resp.get("ticket_ids") or []
        status = "PASS" if passed else "FAIL"
        print(f"          {status:<4} | routed={routed} | tickets={tickets} | {latency:.1f}s")
        if not passed:
            for r in reasons:
                print(f"               - {r}")
        # First 120 chars of the answer for quick eyeballing
        ans = (resp.get("answer") or "").replace("\n", " ")
        print(f"          -> {ans[:140]}{'...' if len(ans) > 140 else ''}\n")

        results.append({
            "case": {"cat": case.cat, "user": case.user, "question": case.question},
            "passed": passed,
            "reasons": reasons,
            "routed_to": routed,
            "ticket_ids": tickets,
            "latency_s": round(latency, 2),
            "answer_preview": ans[:200],
        })

    # Summary
    total = len(results)
    passes = sum(1 for r in results if r["passed"])
    print("=" * 60)
    print(f"TOTAL: {passes}/{total} passed")
    print()
    print(f"{'Category':<18} {'Pass':>5} {'Fail':>5}")
    print("-" * 30)
    for cat, counts in cat_summary.items():
        print(f"{cat:<18} {counts['pass']:>5} {counts['fail']:>5}")

    # Latency stats
    lats = [r["latency_s"] for r in results if r["latency_s"] > 0]
    if lats:
        print()
        print(f"Latency: min={min(lats):.1f}s  median={sorted(lats)[len(lats)//2]:.1f}s  max={max(lats):.1f}s  avg={sum(lats)/len(lats):.1f}s")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"summary": cat_summary, "results": results}, f, indent=2)
        print(f"\nWrote {args.json}")

    return 0 if passes == total else 1


if __name__ == "__main__":
    sys.exit(main())
