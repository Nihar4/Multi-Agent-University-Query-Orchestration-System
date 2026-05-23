"""Router agent — classifies the question and picks a department."""
from __future__ import annotations

import json
from dataclasses import dataclass

from .llm_client import chat, parse_json_object


DEPARTMENTS = [
    ("REGISTRAR", "Enrollment, registration, course add/drop, holds, transcripts."),
    ("ADVISING", "Degree planning, graduation requirements, prerequisites, missing courses."),
    ("FINANCIAL", "Tuition, balance, payment, scholarships, financial holds, FAFSA."),
    ("IT", "Account locked, password, SSO, Wi-Fi, email, technical issues."),
    ("HOUSING", "Dorm, room, meal plan, dining dollars, residence life."),
]


ROUTER_SYSTEM = """\
You are the ROUTING agent of a university multi-agent system.

Your only job: read the student's question and decide which department's
specialist agent should handle it. You do NOT answer the question yourself.

Available departments:
""" + "\n".join(f"  - {code}: {desc}" for code, desc in DEPARTMENTS) + """

Respond with ONLY a JSON object, no prose, no code fences:
{
  "department": "REGISTRAR" | "ADVISING" | "FINANCIAL" | "IT" | "HOUSING",
  "confidence": 0.0-1.0,
  "reason": "one short sentence"
}

Routing hints:
- "Why can't I enroll" or "register for ..." → REGISTRAR (it checks holds + prereqs and can pull data from other departments via its tools).
- "What courses do I still need to graduate" → ADVISING.
- "Why is there a hold" → if clearly about money/balance → FINANCIAL, otherwise REGISTRAR.
- "I can't log in" / "password" / "Wi-Fi" → IT.
- "Dorm" / "meal plan" / "dining" → HOUSING.
- If genuinely ambiguous, pick REGISTRAR (it has the broadest read-only view).
"""


@dataclass
class RoutingDecision:
    department: str
    confidence: float
    reason: str


def route(question: str) -> RoutingDecision:
    messages = [
        {"role": "system", "content": ROUTER_SYSTEM},
        {"role": "user", "content": question},
    ]
    resp = chat(messages=messages, temperature=0.0, max_tokens=200)
    content = (resp.choices[0].message.content or "").strip()
    try:
        data = parse_json_object(content)
        dept = str(data.get("department", "REGISTRAR")).upper()
        if dept not in {code for code, _ in DEPARTMENTS}:
            dept = "REGISTRAR"
        return RoutingDecision(
            department=dept,
            confidence=float(data.get("confidence", 0.5)),
            reason=str(data.get("reason", ""))[:200],
        )
    except (ValueError, json.JSONDecodeError, TypeError):
        return RoutingDecision(department="REGISTRAR", confidence=0.0, reason="router-fallback")
