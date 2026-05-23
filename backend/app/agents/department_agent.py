"""Base department-agent class.

Each department agent:
  - Owns its own tool set (DB-access functions).
  - Owns its own knowledge base (policy text).
  - Runs a tool-calling loop against the LLM until it produces a final answer
    OR decides the question cannot be resolved (in which case it returns a
    structured "needs_ticket" signal so the orchestrator creates a ticket).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from .llm_client import chat
from .tools import ToolEntry, dispatch, tool_schemas


@dataclass
class AgentResult:
    answer: str
    needs_ticket: bool
    suggested_subject: str
    summary_for_department: str
    trace: list[str]


class DepartmentAgent:
    """Generic department agent driven by a system prompt + tools + KB."""

    def __init__(
        self,
        *,
        code: str,
        name: str,
        knowledge_base: str,
        tools: dict[str, ToolEntry],
    ) -> None:
        self.code = code
        self.name = name
        self.knowledge_base = knowledge_base
        self.tools = tools

    # ---- prompts ----------------------------------------------------------

    def _system_prompt(self, student_context: str) -> str:
        return f"""\
You are the AI agent for the **{self.name}** ({self.code}) department of Mock University.

You handle questions in YOUR department's scope only. Use the tools provided
to read real student data from the university database before answering.
NEVER invent data — if you need a fact, call a tool.

# Knowledge base (department policy)
{self.knowledge_base}

# Student context
{student_context}

# How to answer
1. Decide which tools you need to answer the question. Call them.
2. Reason over the tool results.
3. If you can confidently answer, write a clear, friendly explanation for the
   student. Cite the specific data point (e.g., "your balance of $1,250.75 is
   past due"). Suggest concrete next steps.
4. If the question requires human action a tool cannot perform (e.g., "please
   reset my password", "please remove this hold"), say so and end your final
   message with the JSON tag:
   <ESCALATE>{{"subject": "...", "summary": "..."}}</ESCALATE>
   where subject is a one-line ticket title and summary is a 2-4 sentence
   briefing for the human staffer that includes the relevant data you found.

Keep your final answer concise (3-8 sentences). Use plain language a student
will understand. Do NOT add disclaimers about being an AI.
"""

    # ---- tool-calling loop ------------------------------------------------

    def run(
        self,
        db: Session,
        student_id: int,
        student_context: str,
        question: str,
        max_iters: int = 4,
    ) -> AgentResult:
        trace: list[str] = [f"Routed to {self.code} agent."]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt(student_context)},
            {"role": "user", "content": question},
        ]
        schemas = tool_schemas(self.tools)

        for step in range(max_iters):
            resp = chat(messages=messages, tools=schemas, temperature=0.2, max_tokens=1024)
            choice = resp.choices[0]
            msg = choice.message

            tool_calls = getattr(msg, "tool_calls", None) or []
            if tool_calls:
                # Append assistant message containing the tool calls
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ],
                })
                # Execute each tool and append a tool-role message
                for tc in tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = dispatch(name, self.tools, db, student_id, args)
                    trace.append(f"{self.code}.{name}({json.dumps(args)}) -> {json.dumps(result)[:160]}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    })
                continue  # loop to let the model read tool outputs

            # No more tool calls — this is the final answer.
            content = (msg.content or "").strip()
            needs_ticket, subject, summary, clean_answer = _parse_escalation(content)
            return AgentResult(
                answer=clean_answer,
                needs_ticket=needs_ticket,
                suggested_subject=subject,
                summary_for_department=summary,
                trace=trace,
            )

        # Hit max iterations without finalizing — escalate.
        return AgentResult(
            answer="I gathered some information but couldn't fully resolve this. I'll create a ticket so the department can follow up.",
            needs_ticket=True,
            suggested_subject="Unresolved student query",
            summary_for_department=f"Agent ran out of iterations. Original question: {question!r}",
            trace=trace + ["max_iters reached without final answer"],
        )


def _parse_escalation(content: str) -> tuple[bool, str, str, str]:
    """Look for an <ESCALATE>{...}</ESCALATE> tag at the end of the answer."""
    tag = "<ESCALATE>"
    end_tag = "</ESCALATE>"
    if tag in content and end_tag in content:
        start = content.find(tag) + len(tag)
        end = content.find(end_tag, start)
        raw = content[start:end].strip()
        clean = (content[: content.find(tag)] + content[end + len(end_tag):]).strip()
        try:
            data = json.loads(raw)
            return True, data.get("subject", "Student query"), data.get("summary", ""), clean
        except json.JSONDecodeError:
            return True, "Student query", raw, clean
    return False, "", "", content
