"""LangGraph agent architecture.

Two graph layers:

  1. **Department sub-graph** (one per dept, built per request)
       agent  ⇄  tools_node   (React-style loop until no more tool calls)
     Each dept gets its own KB-aware system prompt and its own scoped tools.

  2. **Top-level orchestration graph**
       classify → {smalltalk | run_departments} → synthesize → create_tickets → finalize

The classifier decides:
  - kind = "smalltalk" → general agent answers, no DB, no ticket
  - kind = "single"    → one department agent handles it
  - kind = "multi"     → multiple department agents each handle a slice,
                         then a synthesizer combines their answers

Each department agent can independently emit <ESCALATE>{...}</ESCALATE>
at the end of its final answer to signal "I need human action on this".
The create_tickets node turns each escalation into a ticket for that dept.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from sqlalchemy.orm import Session

from ..models import ChatMessage, Department, Student, Ticket, TicketMessage
from .knowledge_base import KB_BY_CODE
from .lc_llm import get_chat_llm
from .lc_tools import DEPT_TOOL_BUILDERS

log = logging.getLogger("agents.graph")

# Map dept code → human-readable name (used in prompts and the API response)
DEPT_NAMES = {
    "REGISTRAR": "Office of the Registrar",
    "ADVISING": "Academic Advising Center",
    "FINANCIAL": "Financial Aid & Bursar",
    "IT": "IT Help Desk",
    "HOUSING": "Housing & Dining Services",
}

DEPT_BLURBS = {
    "REGISTRAR": "Enrollment, registration, course add/drop, holds (any kind), transcripts, registration windows.",
    "ADVISING":  "Degree planning, graduation requirements, prerequisites, missing courses, academic probation, capstone.",
    "FINANCIAL": "Tuition, balance, payment plans, refunds, scholarships, financial holds, FAFSA, billing.",
    "IT":        "Account locked, password, SSO, Wi-Fi, email quota, technical access issues.",
    "HOUSING":   "Dorm assignment, room change, meal plan, dining dollars, residence life.",
}


# ----------------------------------------------------------------------------
# Department sub-graph
# ----------------------------------------------------------------------------

class _DeptState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def _dept_system_prompt(dept_code: str, student_context: str) -> str:
    name = DEPT_NAMES[dept_code]
    kb = KB_BY_CODE[dept_code]
    return f"""\
You are the AI agent for the **{name}** ({dept_code}) department of Mock University.

You handle questions in YOUR department's scope only. Use the tools provided
to read real student data from the university database before answering.
NEVER invent data — if you need a fact, call a tool.

# IMPORTANT — Data scope (security)
Every tool you have is hard-scoped to the CURRENTLY LOGGED-IN STUDENT below.
You CANNOT access any other student's records. If the question asks about a
different person (by name, email, student number such as S1002, or "my
friend"), refuse politely: "I can only access your own records." Do NOT
call tools to satisfy such a request and do NOT relabel your own data as if
it were someone else's. The tool results always belong to THIS student.

# Knowledge base (department policy)
{kb}

# Currently logged-in student (the only person you have data for)
{student_context}

# How to answer
1. Decide which of your tools you need. Call them.
2. Reason over the tool results.
3. Write the answer — see STYLE below.
4. ESCALATION RULE — when to open a ticket. End your final message with
   <ESCALATE>{{"subject": "...", "summary": "..."}}</ESCALATE> if the
   student is REQUESTING that something be changed, fixed, or done, and
   your tools cannot perform that change themselves. Trigger this for:
     - imperative verbs ("unlock my account", "remove the hold", "drop the
       class", "move me out", "approve a late drop")
     - declared intent ("I want to defer / withdraw / transfer / change my
       major / move dorms / declare a minor")
     - "I need to ..." / "I'd like to ..." / "Can you / can I (still) ..."
       when the answer requires staff to make a change
     - any request to bypass a deadline / policy / requirement ("but the
       deadline passed", "after the cutoff", "even though I'm late") —
       always escalate even if your tool reports the request can't be done
       automatically
   Do NOT escalate for pure information lookups ("what is", "how much",
   "is there a", "what grade did I get", "am I on probation"). Do NOT
   escalate hypotheticals — phrases like "can I (in general)", "would I
   be able to", "is it possible", "hypothetically", "what happens if I"
   are asking about policy, not requesting action.
     - subject: 1-line title
     - summary: 2-3 sentence briefing for staff with the relevant data

# STYLE — match the question's casualness
- 2-4 sentences. Plain language. Talk like a helpful TA, not a policy memo.
- Skip section headers ("**Next steps:**", "**What to do:**").
- NO bullet lists unless you're listing 3+ distinct concrete items (e.g.
  4 holds, 5 missing courses). Two items inline in a sentence reads better.
- Bold sparingly — at most one or two key facts.
- Don't restate the question. Don't add an AI disclaimer. Don't end with
  "If you have any other questions, let me know!".
- If the question is partly about other departments, answer ONLY your slice
  briefly. The synthesizer combines slices.
"""


def build_dept_graph(dept_code: str, db: Session, student: Student):
    """Build (and compile) a per-request department sub-graph."""
    llm = get_chat_llm(temperature=0.2, max_tokens=1024)
    tools = DEPT_TOOL_BUILDERS[dept_code](db, student.id)
    llm_with_tools = llm.bind_tools(tools)

    def _agent_node(state: _DeptState) -> dict[str, Any]:
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    def _should_continue(state: _DeptState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            return "tools"
        return END

    builder = StateGraph(_DeptState)
    builder.add_node("agent", _agent_node)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")
    return builder.compile()


# ----------------------------------------------------------------------------
# Top-level orchestration graph
# ----------------------------------------------------------------------------

@dataclass
class DeptResult:
    code: str
    answer: str               # the plain prose part (without ESCALATE tag)
    needs_ticket: bool
    subject: str
    summary: str
    tool_trace: list[str] = field(default_factory=list)


class TopState(TypedDict, total=False):
    question: str
    student_id: int
    # Routing
    kind: str                  # "smalltalk" | "single" | "multi"
    departments: list[str]
    routing_reason: str
    # Execution
    dept_results: list[DeptResult]
    smalltalk_answer: str
    # Final
    final_answer: str
    tickets_created: list[int]
    trace: list[str]


# ---- classify node ----------------------------------------------------------

_CLASSIFY_PROMPT = """\
You are the ROUTING agent of a university multi-agent student-support system.

Your job is to look at the student's question and decide:
  - whether it's casual small talk (greetings, thanks, "what can you do",
    "who are you", goodbye) that needs NO department,
  - which department(s) need to be involved if it's a real question,
  - if multiple departments are needed, list ALL of them.

Available departments:
""" + "\n".join(f"  - {c}: {DEPT_BLURBS[c]}" for c in DEPT_NAMES) + """

Respond with ONLY a JSON object (no prose, no code fences):
{
  "kind": "smalltalk" | "single" | "multi",
  "departments": ["REGISTRAR" | "ADVISING" | "FINANCIAL" | "IT" | "HOUSING", ...],
  "reason": "one short sentence"
}

Rules:
- smalltalk → "departments": []
- single → exactly one department
- multi  → 2 or more departments. Pick MULTI only if the question genuinely
  spans different concerns.

HARD RULES (override the soft preferences below):
- If the question LITERALLY NAMES two or more departments / domains
  ("financial hold AND advising hold", "academic and financial", "Registrar
  and the Bursar", "IT and Registrar"), you MUST pick multi with all of
  the named departments. Do not collapse into single because one dept's
  tools can read the same data — answer attribution matters.
- "Clear my financial AND advising holds" → multi: FINANCIAL + ADVISING.
- "Both my X hold and Y hold" → multi: dept(X) + dept(Y).

Examples of multi:
  * "I want to defer/withdraw" → REGISTRAR + FINANCIAL + HOUSING
  * "Can I change dorms if I owe money" → HOUSING + FINANCIAL
  * "I'm locked out and registration opens tomorrow" → IT + REGISTRAR
  * "What do I need to graduate next term" → ADVISING + REGISTRAR
- Do not invent departments outside the list. If unsure between single
  options, pick the best fit.

EXTRA SIGNALS for multi-dept routing:
- If the question names two DIFFERENT kinds of holds (e.g. "financial hold AND
  advising hold"), include BOTH FINANCIAL and ADVISING.
- If the question mentions a locked/login/SSO issue AND mentions registration,
  include BOTH IT and REGISTRAR.
- If the question asks the system to "handle everything" or to do multiple
  follow-up actions, include every department that owns one of those actions.
- If the question asks about an interaction between two domains (e.g. "if I
  drop X how does it affect my aid"), include both ADVISING and FINANCIAL.
- If the question explicitly contrasts TWO kinds of blockers ("academic AND
  financial", "billing AND registration"), include the department that owns
  each side — even though Registrar can read all holds, the human-facing
  answer is clearer when both departments contribute.
"""

_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _parse_routing(content: str) -> tuple[str, list[str], str]:
    """Extract (kind, departments, reason) from the classifier LLM output."""
    m = _JSON_RE.search(content)
    if not m:
        return ("single", ["REGISTRAR"], "fallback: no JSON in router output")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return ("single", ["REGISTRAR"], "fallback: bad JSON")
    kind = str(data.get("kind", "single")).lower()
    if kind not in ("smalltalk", "single", "multi"):
        kind = "single"
    depts_raw = data.get("departments") or []
    depts: list[str] = []
    for d in depts_raw:
        d = str(d).upper().strip()
        if d in DEPT_NAMES:
            depts.append(d)
    # Sanity: smalltalk → no depts; single → 1; multi → ≥2
    if kind == "smalltalk":
        depts = []
    elif kind == "single":
        depts = depts[:1] if depts else ["REGISTRAR"]
    elif kind == "multi":
        if len(depts) < 2:
            kind = "single"
            depts = depts[:1] if depts else ["REGISTRAR"]
    reason = str(data.get("reason", ""))[:200]
    return (kind, depts, reason)


def _rule_based_routing_hints(question: str) -> list[str]:
    """Deterministic patterns that ALWAYS imply specific departments.

    Catches cases where the LLM router consolidates into a single dept even
    when the question literally names multiple. Result is merged with the
    LLM's output (not replacing it).
    """
    ql = question.lower()
    forced: list[str] = []

    # Hold-type signals
    if "financial hold" in ql or "billing hold" in ql or "bursar hold" in ql:
        forced.append("FINANCIAL")
    if "advising hold" in ql:
        forced.append("ADVISING")
    if "registration hold" in ql or "registrar hold" in ql:
        forced.append("REGISTRAR")
    if "it hold" in ql or "account hold" in ql or "sso hold" in ql:
        forced.append("IT")

    # "Account status" or login/SSO/lockout context alongside registration
    # → must include both IT (account) and REGISTRAR (registration).
    has_account_word = any(s in ql for s in ["account status", "account access",
                                              "my account", "locked out", "log in",
                                              "sso", "login"])
    has_register_word = any(s in ql for s in ["register", "registration",
                                              "enroll", "registration window"])
    if has_account_word and has_register_word:
        if "IT" not in forced:
            forced.append("IT")
        if "REGISTRAR" not in forced:
            forced.append("REGISTRAR")

    # "Academic AND financial" / "GPA AND aid" pairings
    if ("academic" in ql or "gpa" in ql or "grade" in ql or "grades" in ql) and (
        "financial" in ql or "aid" in ql or "scholarship" in ql or "tuition" in ql or "balance" in ql
    ):
        if "ADVISING" not in forced:
            forced.append("ADVISING")
        if "FINANCIAL" not in forced:
            forced.append("FINANCIAL")

    # Big life events that ALWAYS span Registrar + Financial + Housing (and
    # sometimes Advising). Catch them even when the student doesn't name the
    # affected departments.
    DEFER_WORDS = ["defer", "deferral", "take a semester off", "take time off",
                   "leave of absence"]
    WITHDRAW_WORDS = ["withdraw", "withdrawal", "dropping out", "drop out"]
    TRANSFER_WORDS = ["transfer", "transferring"]

    if any(w in ql for w in DEFER_WORDS) or any(w in ql for w in WITHDRAW_WORDS):
        for d in ("REGISTRAR", "FINANCIAL", "HOUSING"):
            if d not in forced:
                forced.append(d)

    if any(w in ql for w in TRANSFER_WORDS):
        # Transfer touches Registrar (transcript), Financial (refund), and
        # Advising (degree audit / equivalencies).
        for d in ("REGISTRAR", "FINANCIAL", "ADVISING"):
            if d not in forced:
                forced.append(d)

    # "Change my major" → ADVISING + REGISTRAR.
    if ("change my major" in ql or "switch my major" in ql or "change major" in ql
            or "switch major" in ql or "declare a minor" in ql or "declare a major" in ql):
        for d in ("ADVISING", "REGISTRAR"):
            if d not in forced:
                forced.append(d)

    return forced


def _classify_node(state: TopState) -> dict[str, Any]:
    llm = get_chat_llm(temperature=0.0, max_tokens=300)
    msg = llm.invoke([
        SystemMessage(content=_CLASSIFY_PROMPT),
        HumanMessage(content=state["question"]),
    ])
    kind, depts, reason = _parse_routing(msg.content or "")

    # Apply rule-based hints: if the question literally names multiple hold
    # types or departments, force the union with the LLM's choice.
    hints = _rule_based_routing_hints(state["question"])
    if hints:
        merged = list(dict.fromkeys(depts + hints))  # dedup preserve order
        if len(merged) >= 2:
            kind = "multi"
        depts = merged
        reason = f"{reason} [+rule hints: {hints}]"

    trace = list(state.get("trace") or [])
    trace.append(f"classify: kind={kind} depts={depts} — {reason}")
    return {"kind": kind, "departments": depts, "routing_reason": reason, "trace": trace}


# ---- smalltalk node ---------------------------------------------------------

_SMALLTALK_PROMPT = """\
You're the friendly front-desk AI of Mock University.

Reply in 1-2 short sentences. Match the casualness. For "what can you do",
mention you help with enrollment, holds, billing, IT, graduation, housing.
Don't claim to have looked up any data — you didn't. No emojis. No "feel
free to reach out anytime!" filler.
"""


def _smalltalk_node(state: TopState) -> dict[str, Any]:
    llm = get_chat_llm(temperature=0.4, max_tokens=200)
    msg = llm.invoke([
        SystemMessage(content=_SMALLTALK_PROMPT),
        HumanMessage(content=state["question"]),
    ])
    text = (msg.content or "Hi! How can I help you today?").strip()
    trace = list(state.get("trace") or [])
    trace.append("smalltalk: handled by general agent (no routing).")
    return {"smalltalk_answer": text, "trace": trace}


# ---- run_departments node ---------------------------------------------------

_ESCALATE_RE_CLOSED = re.compile(r"<\s*ESCALATE\s*>([\s\S]*?)<\s*/\s*ESCALATE\s*>", re.IGNORECASE)
_ESCALATE_RE_OPEN = re.compile(r"<\s*ESCALATE\s*>", re.IGNORECASE)


def _parse_dept_output(content: str) -> tuple[str, bool, str, str]:
    """Extract (clean_answer, needs_ticket, subject, summary) from a dept agent's final message.

    Handles three cases:
      1. Well-formed:   <ESCALATE>{...}</ESCALATE>
      2. Missing close: <ESCALATE>{...}            (LLM forgot the closing tag)
      3. No tag at all.
    """
    # Case 1: well-formed tag
    m = _ESCALATE_RE_CLOSED.search(content)
    if m:
        raw = m.group(1).strip()
        clean = (content[: m.start()] + content[m.end():]).strip()
        return _finish_escalation(raw, clean, content)

    # Case 2: opening tag but no closing — try to find the JSON object after it.
    m_open = _ESCALATE_RE_OPEN.search(content)
    if m_open:
        tail = content[m_open.end():].strip()
        # Find first balanced {...} block in the tail
        first_brace = tail.find("{")
        last_brace = tail.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            raw = tail[first_brace : last_brace + 1]
            clean = (content[: m_open.start()] + tail[last_brace + 1:]).strip()
            return _finish_escalation(raw, clean, content)

    # Case 3: no escalation
    return content.strip(), False, "", ""


def _finish_escalation(raw: str, clean: str, original: str) -> tuple[str, bool, str, str]:
    try:
        data = json.loads(raw)
        subject = str(data.get("subject", "Student query"))[:200]
        summary = str(data.get("summary", "")).strip()
    except json.JSONDecodeError:
        subject, summary = "Student query", raw
    if not clean:
        clean = summary or "I've forwarded your request so the right team can take it from here."
    return clean, True, subject, summary


def _student_context(student: Student) -> str:
    return (
        f"Name: {student.full_name}\n"
        f"Student ID: {student.student_number}\n"
        f"Major: {student.major}\n"
        f"Year: {student.year}\n"
        f"GPA: {student.gpa}\n"
    )


def _build_run_departments(db: Session, student: Student):
    def _node(state: TopState) -> dict[str, Any]:
        results: list[DeptResult] = []
        trace = list(state.get("trace") or [])
        question = state["question"]
        for code in state["departments"]:
            try:
                subgraph = build_dept_graph(code, db, student)
                sys_prompt = _dept_system_prompt(code, _student_context(student))
                out = subgraph.invoke(
                    {"messages": [
                        SystemMessage(content=sys_prompt),
                        HumanMessage(content=question),
                    ]},
                    config={"recursion_limit": 12},
                )
                final = out["messages"][-1]
                content = final.content if isinstance(final.content, str) else str(final.content)
                clean, needs_ticket, subject, summary = _parse_dept_output(content)
                # Capture tool calls in the trace
                tool_trace: list[str] = []
                for m in out["messages"]:
                    if isinstance(m, AIMessage) and m.tool_calls:
                        for tc in m.tool_calls:
                            tool_trace.append(f"{code}.{tc['name']}({json.dumps(tc['args'])[:80]})")
                results.append(DeptResult(
                    code=code,
                    answer=clean,
                    needs_ticket=needs_ticket,
                    subject=subject,
                    summary=summary,
                    tool_trace=tool_trace,
                ))
                trace.append(f"{code}: {len(tool_trace)} tool call(s); ticket={'yes' if needs_ticket else 'no'}")
            except Exception as exc:  # noqa: BLE001
                log.exception("dept %s failed", code)
                results.append(DeptResult(
                    code=code,
                    answer=f"(The {code} agent hit an error: {exc})",
                    needs_ticket=False,
                    subject="",
                    summary="",
                ))
                trace.append(f"{code}: ERROR {exc}")
        return {"dept_results": results, "trace": trace}
    return _node


# ---- synthesize node --------------------------------------------------------

_SYNTH_PROMPT = """\
Combine the department agents' slices into ONE crisp reply to the student.

Rules:
- 3-6 sentences total. Plain student-friendly language.
- Mention each department's contribution in ONE sentence each.
- One short closing sentence with the single most important next step.
- NO section headers. NO bullet lists unless absolutely necessary.
- Don't restate the question. Don't add AI disclaimers. Don't echo the
  individual agents verbatim — paraphrase tightly.
- Only use facts the agents provided. Don't invent.
"""


def _synthesize_node(state: TopState) -> dict[str, Any]:
    results = state.get("dept_results") or []
    trace = list(state.get("trace") or [])
    if not results:
        return {"final_answer": "Sorry, I couldn't get any department to respond.", "trace": trace}

    if len(results) == 1:
        # Single dept — just pass through, no synthesizer call.
        trace.append("synthesize: single dept — pass-through")
        return {"final_answer": results[0].answer, "trace": trace}

    # Multiple depts — ask LLM to combine.
    parts = []
    for r in results:
        parts.append(f"### {r.code} ({DEPT_NAMES[r.code]}) said:\n{r.answer}")
    combined = "\n\n".join(parts)

    llm = get_chat_llm(temperature=0.3, max_tokens=1024)
    msg = llm.invoke([
        SystemMessage(content=_SYNTH_PROMPT),
        HumanMessage(content=f"Question: {state['question']}\n\nDepartment answers:\n\n{combined}"),
    ])
    text = (msg.content or combined).strip()
    trace.append(f"synthesize: combined {len(results)} dept answers")
    return {"final_answer": text, "trace": trace}


# ---- create_tickets node ----------------------------------------------------

def _build_create_tickets(db: Session, student: Student):
    def _node(state: TopState) -> dict[str, Any]:
        created: list[int] = []
        trace = list(state.get("trace") or [])
        for r in state.get("dept_results") or []:
            if not r.needs_ticket:
                continue
            dept = db.query(Department).filter(Department.code == r.code).first()
            if dept is None:
                continue
            subject = (r.subject or f"Student query for {r.code}")[:200]
            summary = r.summary or f"Student asked: {state['question']}"
            ticket = Ticket(
                student_id=student.id,
                department_id=dept.id,
                subject=subject,
                summary=summary,
                original_question=state["question"],
                status="open",
            )
            db.add(ticket)
            db.flush()
            db.add(TicketMessage(ticket_id=ticket.id, sender="student", body=state["question"]))
            db.add(TicketMessage(
                ticket_id=ticket.id,
                sender="agent",
                body=f"Triaged by {r.code} agent. Summary for staff:\n\n{summary}",
            ))
            created.append(ticket.id)
            trace.append(f"ticket #{ticket.id} created for {r.code}")
        if created:
            db.commit()
        return {"tickets_created": created, "trace": trace}
    return _node


# ---- finalize node ----------------------------------------------------------

def _build_finalize(db: Session, student: Student):
    def _node(state: TopState) -> dict[str, Any]:
        trace = list(state.get("trace") or [])
        # Persist user message
        db.add(ChatMessage(student_id=student.id, role="user", content=state["question"]))

        # Build the final outgoing answer
        if state.get("kind") == "smalltalk":
            answer = state.get("smalltalk_answer") or "Hi!"
            routed = ["GENERAL"]
        else:
            answer = state.get("final_answer") or "Sorry, no answer."
            routed = list(state.get("departments") or [])

        tickets = state.get("tickets_created") or []
        if tickets:
            ticket_phrase = (
                f"I've opened ticket #{tickets[0]} so the team can follow up directly."
                if len(tickets) == 1
                else f"I've opened {len(tickets)} tickets (#{', #'.join(str(t) for t in tickets)}) "
                     f"with the relevant departments so they can follow up."
            )
            if "ticket" not in answer.lower():
                answer = f"{answer}\n\n{ticket_phrase}"

        # Persist assistant message (use first ticket as the "primary" link)
        db.add(ChatMessage(
            student_id=student.id,
            role="assistant",
            content=answer,
            routed_to=",".join(routed),
            ticket_id=tickets[0] if tickets else None,
        ))
        db.commit()

        trace.append("finalize: persisted user + assistant messages")
        return {"final_answer": answer, "trace": trace, "departments": routed}
    return _node


# ----------------------------------------------------------------------------
# Top-graph builder (called per request because some nodes close over db)
# ----------------------------------------------------------------------------

def build_top_graph(db: Session, student: Student):
    builder = StateGraph(TopState)
    builder.add_node("classify", _classify_node)
    builder.add_node("smalltalk", _smalltalk_node)
    builder.add_node("run_departments", _build_run_departments(db, student))
    builder.add_node("synthesize", _synthesize_node)
    builder.add_node("create_tickets", _build_create_tickets(db, student))
    builder.add_node("finalize", _build_finalize(db, student))

    builder.add_edge(START, "classify")

    def _route_after_classify(state: TopState) -> str:
        return "smalltalk" if state.get("kind") == "smalltalk" else "run_departments"

    builder.add_conditional_edges(
        "classify",
        _route_after_classify,
        {"smalltalk": "smalltalk", "run_departments": "run_departments"},
    )
    builder.add_edge("smalltalk", "finalize")
    builder.add_edge("run_departments", "synthesize")
    builder.add_edge("synthesize", "create_tickets")
    builder.add_edge("create_tickets", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------

@dataclass
class OrchestratorOutput:
    answer: str
    routed_to: list[str]
    ticket_ids: list[int]
    trace: list[str]


def handle_question(db: Session, student: Student, question: str) -> OrchestratorOutput:
    """Run the full agent graph for one question."""
    graph = build_top_graph(db, student)
    initial: TopState = {
        "question": question,
        "student_id": student.id,
        "trace": [],
    }
    out = graph.invoke(initial, config={"recursion_limit": 25})
    return OrchestratorOutput(
        answer=out.get("final_answer") or "",
        routed_to=out.get("departments") or [],
        ticket_ids=out.get("tickets_created") or [],
        trace=out.get("trace") or [],
    )
