# Architecture — diagrams & design notes

This document collects every architectural view of the **Multi-Agent University Query Orchestration System** in one place.  All diagrams are written in **Mermaid** with a consistent palette (black text on soft pastel fills) so they render the same way on GitHub, VS Code preview, or any Mermaid viewer.

> 🎨 **Style key** — every diagram uses the same theme initializer:
> ```text
> %%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
> ```
> Fills (`classDef`): `#E8F1FF` (mobile / I-O), `#FFF4E0` (API / decisions), `#E8FFEF` (agents / LLMs), `#F5E8FF` (data stores), `#FFE8E8` (security).

---

## Table of contents

1. [Context diagram (Level-0)](#context-diagram-level-0)
2. [System architecture (Level-1)](#system-architecture-level-1)
3. [Component diagram — backend](#component-diagram--backend)
4. [Multi-agent orchestration graph](#multi-agent-orchestration-graph)
5. [Per-department agent sub-graph](#per-department-agent-sub-graph)
6. [Class diagram (backend ORM)](#class-diagram-backend-orm)
7. [ER diagram](#er-diagram)
8. [Use-case diagram](#use-case-diagram)
9. [Sequence — single-department direct answer](#sequence--single-department-direct-answer)
10. [Sequence — multi-department combined answer](#sequence--multi-department-combined-answer)
11. [Sequence — multi-department ticket creation](#sequence--multi-department-ticket-creation)
12. [Sequence — small talk](#sequence--small-talk)
13. [Ticket state machine](#ticket-state-machine)
14. [Data flow diagram](#data-flow-diagram)
15. [Deployment diagram](#deployment-diagram)
16. [Android navigation](#android-navigation)
17. [Authentication flow](#authentication-flow)
18. [Tool calling cycle (inside one dept agent)](#tool-calling-cycle-inside-one-dept-agent)

---

## Context diagram (Level-0)

The outermost view — who interacts with the system.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
flowchart LR
  Student((Student))
  Staff((Department<br/>staff))
  Sys[University<br/>Multi-Agent System]
  NIM[NVIDIA NIM<br/>openai/gpt-oss-120b]
  Mock[(Mock University<br/>data sources)]

  Student -- asks any question --> Sys
  Sys -- crisp answer / ticket --> Student
  Sys -- LLM calls --> NIM
  NIM -- tool calls / completions --> Sys
  Sys -- read-only --> Mock
  Sys -- routes tickets --> Staff
  Staff -- replies on tickets --> Sys

  classDef ext fill:#E8F1FF,stroke:#111111,color:#111111
  classDef sys fill:#E8FFEF,stroke:#111111,color:#111111
  classDef store fill:#F5E8FF,stroke:#111111,color:#111111
  class Student,Staff ext
  class Sys sys
  class NIM,Mock store
```

---

## System architecture (Level-1)

The full stack as it runs on a developer laptop.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
flowchart TB
  subgraph Android["Android emulator / device"]
    direction TB
    UI[Compose UI<br/>Login / Signup / Home / Chat / Tickets]
    VM[AppViewModel<br/>StateFlow]
    NM[Retrofit + OkHttp<br/>Moshi]
    DS[(DataStore<br/>JWT)]
    UI <--> VM
    VM <--> NM
    VM <--> DS
  end

  subgraph Backend["Python backend (uvicorn)"]
    direction TB
    API[FastAPI routers<br/>auth / chat / tickets]
    SEC[Security<br/>JWT + bcrypt]
    ORCH[Orchestrator<br/>LangGraph top-graph]
    AGENTS[Department agents<br/>5 specialised LLMs]
    TOOLS[Per-dept tool builders<br/>StructuredTool]
    SEED[Seed]
    DB[(SQLite<br/>university_mock.db)]
    API --> SEC
    API --> ORCH
    ORCH --> AGENTS
    AGENTS --> TOOLS
    TOOLS --> DB
    SEED --> DB
  end

  NIM[(NVIDIA NIM<br/>OpenAI-compatible<br/>openai/gpt-oss-120b)]

  NM -- "HTTP + JWT" --> API
  AGENTS -- "LangChain ChatOpenAI" --> NIM

  classDef mobile fill:#E8F1FF,stroke:#111111,color:#111111
  classDef api fill:#FFF4E0,stroke:#111111,color:#111111
  classDef agent fill:#E8FFEF,stroke:#111111,color:#111111
  classDef store fill:#F5E8FF,stroke:#111111,color:#111111
  class UI,VM,NM,DS mobile
  class API,SEC,SEED api
  class ORCH,AGENTS,TOOLS agent
  class DB,NIM store
```

---

## Component diagram — backend

The modules inside `backend/app/` and how they depend on each other.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
flowchart LR
  subgraph entry["entry"]
    main[main.py]
    config[config.py]
  end

  subgraph api["api/"]
    auth[auth.py]
    chat[chat.py]
    tickets[tickets.py]
  end

  subgraph core["core"]
    sec[security.py]
    db[database.py]
    models[models.py]
    schemas[schemas.py]
    seed[seed.py]
  end

  subgraph agents["agents/"]
    orch[orchestrator.py]
    graph[graph.py]
    kb[knowledge_base.py]
    tools[tools.py]
    lctools[lc_tools.py]
    lcllm[lc_llm.py]
    llmc[llm_client.py]
  end

  main --> config
  main --> auth
  main --> chat
  main --> tickets
  main --> seed
  auth --> sec
  auth --> models
  auth --> schemas
  chat --> sec
  chat --> orch
  chat --> schemas
  tickets --> sec
  tickets --> models
  tickets --> schemas
  sec --> models
  sec --> db
  seed --> models
  seed --> db
  orch --> graph
  graph --> kb
  graph --> lctools
  graph --> lcllm
  graph --> models
  lctools --> tools
  tools --> models
  models --> db

  classDef entry fill:#FFF4E0,stroke:#111111,color:#111111
  classDef api fill:#FFF4E0,stroke:#111111,color:#111111
  classDef core fill:#F5E8FF,stroke:#111111,color:#111111
  classDef agents fill:#E8FFEF,stroke:#111111,color:#111111
  class main,config entry
  class auth,chat,tickets api
  class sec,db,models,schemas,seed core
  class orch,graph,kb,tools,lctools,lcllm,llmc agents
```

---

## Multi-agent orchestration graph

The top-level **LangGraph** `StateGraph`. Every node is either a deterministic Python step or an LLM call with its own prompt. The edges show the actual transitions in `backend/app/agents/graph.py`.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
flowchart TD
  S([START]) --> CLS[classify_node<br/>router LLM<br/>kind + departments]
  CLS -- smalltalk --> ST[smalltalk_node<br/>general LLM]
  CLS -- single / multi --> RUN[run_departments_node<br/>iterate selected dept agents]
  RUN --> SYN[synthesize_node<br/>combine slices LLM]
  SYN --> TIC[create_tickets_node<br/>one ticket per ESCALATE]
  ST --> FIN[finalize_node<br/>persist + format]
  TIC --> FIN
  FIN --> E([END])

  classDef llm fill:#E8FFEF,stroke:#111111,color:#111111
  classDef det fill:#FFF4E0,stroke:#111111,color:#111111
  classDef se fill:#F5E8FF,stroke:#111111,color:#111111
  class CLS,ST,SYN llm
  class RUN,TIC,FIN det
  class S,E se
```

**Routing rules** (in `_parse_routing` + deterministic hints in `graph.py`):

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
flowchart TD
  Q[student question] --> H1{contains<br/>greeting / thanks /<br/>goodbye / "what can you do"?}
  H1 -- yes --> SM[smalltalk]
  H1 -- no --> H2{contains<br/>defer / withdraw?}
  H2 -- yes --> MM1[multi:<br/>REGISTRAR + FINANCIAL + HOUSING]
  H2 -- no --> H3{contains transfer?}
  H3 -- yes --> MM2[multi:<br/>REGISTRAR + FINANCIAL + ADVISING]
  H3 -- no --> H4{contains<br/>change major / declare minor?}
  H4 -- yes --> MM3[multi:<br/>ADVISING + REGISTRAR]
  H4 -- no --> LLM[LLM classifier<br/>picks single or multi]

  classDef cond fill:#FFF4E0,stroke:#111111,color:#111111
  classDef out fill:#E8FFEF,stroke:#111111,color:#111111
  classDef io fill:#E8F1FF,stroke:#111111,color:#111111
  class H1,H2,H3,H4 cond
  class SM,MM1,MM2,MM3,LLM out
  class Q io
```

---

## Per-department agent sub-graph

Each department agent is itself a compiled `StateGraph` built fresh per request (because tools close over the request-scoped DB session + student id). It's the classic React-style **agent loop**.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
stateDiagram-v2
  direction LR
  [*] --> Agent
  Agent: agent_node<br/>llm.bind_tools(dept_tools)
  Agent --> Decision
  Decision: needs tools?
  Decision --> Tools: yes — has tool_calls
  Decision --> Final: no
  Tools: ToolNode<br/>execute DB-scoped tools
  Tools --> Agent
  Final: final assistant message<br/>(may contain <ESCALATE> tag)
  Final --> [*]
```

The agent's system prompt is **assembled per department** from three pieces:

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
flowchart LR
  A[Identity & rules<br/>e.g. "You are the IT Help Desk agent..."]
  B[Department knowledge base<br/>knowledge_base.py KB_BY_CODE]
  C[Student context<br/>name / id / major / year / GPA]
  P[System prompt sent to LLM]
  A --> P
  B --> P
  C --> P

  classDef p fill:#E8FFEF,stroke:#111111,color:#111111
  class A,B,C,P p
```

---

## Class diagram (backend ORM)

The SQLAlchemy models in `backend/app/models.py` — what's stored, what's related.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
classDiagram
  class Student {
    +int id
    +str email
    +str password_hash
    +str full_name
    +str student_number
    +str major
    +int year
    +float gpa
    +str academic_standing
    +int credits_completed
    +datetime created_at
  }
  class Department {
    +int id
    +str code
    +str name
    +str contact_email
    +str description
  }
  class Course {
    +int id
    +str code
    +str name
    +int credits
    +str description
  }
  class Prerequisite {
    +int id
    +int course_id
    +int prereq_course_id
  }
  class Enrollment {
    +int id
    +int student_id
    +int course_id
    +str term
    +str status
  }
  class Grade {
    +int id
    +int student_id
    +int course_id
    +str term
    +str grade
  }
  class Hold {
    +int id
    +int student_id
    +int department_id
    +str hold_type
    +str reason
    +bool active
    +datetime created_at
  }
  class TodoItem {
    +int id
    +int student_id
    +str title
    +str detail
    +datetime due_date
    +bool completed
  }
  class FinancialRecord {
    +int id
    +int student_id
    +float balance_due
    +float tuition_charged
    +float scholarships
    +float last_payment
    +datetime payment_due_date
  }
  class ITAccount {
    +int id
    +int student_id
    +str sso_status
    +int email_used_mb
    +int email_quota_mb
    +str last_login_failure
    +bool wifi_enabled
  }
  class HousingRecord {
    +int id
    +int student_id
    +bool has_housing
    +str building
    +str room
    +str meal_plan
    +float dining_balance
  }
  class GraduationRequirement {
    +int id
    +str major
    +int required_course_id
    +str category
  }
  class Ticket {
    +int id
    +int student_id
    +int department_id
    +str subject
    +str summary
    +str original_question
    +str status
    +datetime created_at
    +datetime updated_at
  }
  class TicketMessage {
    +int id
    +int ticket_id
    +str sender
    +str body
    +datetime created_at
  }
  class ChatMessage {
    +int id
    +int student_id
    +str role
    +str content
    +str routed_to
    +int ticket_id
    +datetime created_at
  }

  Student "1" --> "*" Enrollment
  Student "1" --> "*" Grade
  Student "1" --> "*" Hold
  Student "1" --> "*" TodoItem
  Student "1" --> "1" FinancialRecord
  Student "1" --> "1" ITAccount
  Student "1" --> "1" HousingRecord
  Student "1" --> "*" Ticket
  Student "1" --> "*" ChatMessage
  Department "1" --> "*" Hold
  Department "1" --> "*" Ticket
  Course "1" --> "*" Enrollment
  Course "1" --> "*" Grade
  Course "1" --> "*" Prerequisite : course
  Course "1" --> "*" Prerequisite : prereq
  Course "1" --> "*" GraduationRequirement
  Ticket "1" --> "*" TicketMessage
```

---

## ER diagram

Same domain, drawn as ER.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
erDiagram
  STUDENT ||--o{ ENROLLMENT : has
  STUDENT ||--o{ GRADE : earns
  STUDENT ||--o{ HOLD : has
  STUDENT ||--o{ TODO_ITEM : owns
  STUDENT ||--|| FINANCIAL_RECORD : owns
  STUDENT ||--|| IT_ACCOUNT : owns
  STUDENT ||--|| HOUSING_RECORD : owns
  STUDENT ||--o{ TICKET : opens
  STUDENT ||--o{ CHAT_MESSAGE : sends
  DEPARTMENT ||--o{ HOLD : issues
  DEPARTMENT ||--o{ TICKET : owns
  COURSE ||--o{ ENROLLMENT : in
  COURSE ||--o{ GRADE : recorded_for
  COURSE ||--o{ PREREQUISITE : has
  COURSE ||--o{ GRADUATION_REQUIREMENT : counts_for
  TICKET ||--o{ TICKET_MESSAGE : carries

  STUDENT {
    int id PK
    string email
    string password_hash
    string full_name
    string student_number
    string major
    int year
    float gpa
    string academic_standing
    int credits_completed
  }
  DEPARTMENT {
    int id PK
    string code
    string name
    string contact_email
  }
  COURSE {
    int id PK
    string code
    string name
    int credits
  }
  ENROLLMENT {
    int id PK
    int student_id FK
    int course_id FK
    string term
    string status
  }
  GRADE {
    int id PK
    int student_id FK
    int course_id FK
    string term
    string grade
  }
  HOLD {
    int id PK
    int student_id FK
    int department_id FK
    string hold_type
    string reason
    bool active
  }
  TODO_ITEM {
    int id PK
    int student_id FK
    string title
    datetime due_date
    bool completed
  }
  FINANCIAL_RECORD {
    int id PK
    int student_id FK
    float balance_due
    float scholarships
    datetime payment_due_date
  }
  IT_ACCOUNT {
    int id PK
    int student_id FK
    string sso_status
    int email_used_mb
    bool wifi_enabled
  }
  HOUSING_RECORD {
    int id PK
    int student_id FK
    string building
    string room
    string meal_plan
    float dining_balance
  }
  PREREQUISITE {
    int id PK
    int course_id FK
    int prereq_course_id FK
  }
  GRADUATION_REQUIREMENT {
    int id PK
    string major
    int required_course_id FK
    string category
  }
  TICKET {
    int id PK
    int student_id FK
    int department_id FK
    string subject
    string status
  }
  TICKET_MESSAGE {
    int id PK
    int ticket_id FK
    string sender
    string body
  }
  CHAT_MESSAGE {
    int id PK
    int student_id FK
    string role
    string content
    string routed_to
    int ticket_id FK
  }
```

---

## Use-case diagram

The actor / use-case view — what the student (and, indirectly, staff) can do.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
flowchart LR
  S((Student))
  D((Department<br/>staff))

  subgraph sys["University Multi-Agent System"]
    U1((Sign up))
    U2((Log in))
    U3((View profile))
    U4((Ask question<br/>natural language))
    U5((Get crisp answer<br/>single dept))
    U6((Get combined answer<br/>multi dept))
    U7((Auto-open<br/>1+ tickets))
    U8((View ticket list))
    U9((View ticket detail))
    U10((Reply on ticket))
    U11((View chat history))
    U12((Handle ticket))
  end

  S --> U1
  S --> U2
  S --> U3
  S --> U4
  S --> U8
  S --> U9
  S --> U10
  S --> U11
  U4 --> U5
  U4 --> U6
  U4 --> U7
  D --> U12

  classDef actor fill:#E8F1FF,stroke:#111111,color:#111111
  classDef uc fill:#E8FFEF,stroke:#111111,color:#111111
  class S,D actor
  class U1,U2,U3,U4,U5,U6,U7,U8,U9,U10,U11,U12 uc
```

---

## Sequence — single-department direct answer

_"What classes am I in this semester?"_  → REGISTRAR handles it via one tool call, no ticket.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
sequenceDiagram
  autonumber
  actor Student
  participant App as Android (Compose)
  participant API as FastAPI /chat
  participant Top as Top StateGraph
  participant Cls as Classifier LLM
  participant Reg as Registrar agent
  participant Tool as ToolNode
  participant DB as SQLite
  participant NIM as NVIDIA NIM

  Student->>App: types "what classes am I in?"
  App->>API: POST /chat (JWT)
  API->>Top: handle_question(student, msg)
  Top->>Cls: classify
  Cls->>NIM: completion
  NIM-->>Cls: {kind:single, depts:[REGISTRAR]}
  Cls-->>Top: routing decision
  Top->>Reg: run sub-graph
  Reg->>NIM: chat w/ tools
  NIM-->>Reg: tool_call(reg_get_current_enrollment)
  Reg->>Tool: execute
  Tool->>DB: SELECT enrollments WHERE student_id=...
  DB-->>Tool: rows
  Tool-->>Reg: {enrolled_courses:[...]}
  Reg->>NIM: chat w/ tool result
  NIM-->>Reg: "You're currently enrolled in CS301 and CS370."
  Reg-->>Top: final answer
  Top->>DB: INSERT chat_messages (user + assistant)
  Top-->>API: OrchestratorOutput
  API-->>App: {answer, routed_to:[REGISTRAR], ticket_ids:[]}
  App-->>Student: renders bubble with "via REGISTRAR" chip
```

---

## Sequence — multi-department combined answer

_"If I drop MATH152 how does that affect my degree progress and my financial aid?"_  → ADVISING + FINANCIAL, no tickets.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
sequenceDiagram
  autonumber
  actor Student
  participant App
  participant API as FastAPI /chat
  participant Top as Top StateGraph
  participant Cls as Classifier LLM
  participant Adv as Advising agent
  participant Fin as Financial agent
  participant Syn as Synthesizer LLM
  participant DB

  Student->>App: question
  App->>API: POST /chat
  API->>Top: handle_question
  Top->>Cls: classify
  Cls-->>Top: {kind:multi, depts:[ADVISING, FINANCIAL]}
  Top->>Adv: run sub-graph (parallel logically, sequential physically)
  Adv->>DB: graduation_progress + transcript
  Adv-->>Top: advising slice
  Top->>Fin: run sub-graph
  Fin->>DB: account + holds
  Fin-->>Top: financial slice
  Top->>Syn: combine slices
  Syn-->>Top: unified reply
  Top->>DB: persist chat
  Top-->>API: {answer, routed_to:[ADVISING, FINANCIAL], ticket_ids:[]}
  API-->>App: response
  App-->>Student: bubble with "via ADVISING + FINANCIAL" chip
```

---

## Sequence — multi-department ticket creation

_"I need to defer for a semester"_  → REGISTRAR + FINANCIAL + HOUSING each open their own ticket.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
sequenceDiagram
  autonumber
  actor Student
  participant App
  participant API as FastAPI /chat
  participant Top as Top StateGraph
  participant Cls as Classifier LLM
  participant Reg as Registrar agent
  participant Fin as Financial agent
  participant Hou as Housing agent
  participant Syn as Synthesizer LLM
  participant Tk as create_tickets_node
  participant DB

  Student->>App: "I need to defer for a semester"
  App->>API: POST /chat
  API->>Top: handle_question
  Top->>Cls: classify
  Note over Cls: rule "defer" → multi
  Cls-->>Top: {kind:multi, depts:[REGISTRAR, FINANCIAL, HOUSING]}
  Top->>Reg: run sub-graph
  Reg-->>Top: answer + <ESCALATE>
  Top->>Fin: run sub-graph
  Fin-->>Top: answer + <ESCALATE>
  Top->>Hou: run sub-graph
  Hou-->>Top: answer + <ESCALATE>
  Top->>Syn: combine 3 slices
  Syn-->>Top: unified reply
  Top->>Tk: create 1 ticket per ESCALATE
  Tk->>DB: INSERT tickets x3 + ticket_messages
  Tk-->>Top: ticket_ids=[42,43,44]
  Top->>DB: persist chat (ticket_ids in reply)
  Top-->>API: {answer, routed_to:[REG,FIN,HOUSING], ticket_ids:[42,43,44]}
  API-->>App: response
  App-->>Student: bubble + "View ticket #42 / #43 / #44" links
```

---

## Sequence — small talk

_"Thanks!"_ — never touches a department or the DB.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
sequenceDiagram
  autonumber
  actor Student
  participant App
  participant API as FastAPI /chat
  participant Top as Top StateGraph
  participant Cls as Classifier LLM
  participant ST as Smalltalk LLM
  participant DB

  Student->>App: "thanks!"
  App->>API: POST /chat
  API->>Top: handle_question
  Top->>Cls: classify
  Cls-->>Top: {kind:smalltalk, depts:[]}
  Top->>ST: generate friendly reply
  ST-->>Top: "No problem! Let me know if you need anything."
  Top->>DB: persist chat (routed_to=GENERAL)
  Top-->>API: {answer, routed_to:[GENERAL], ticket_ids:[]}
  API-->>App: response
```

---

## Ticket state machine

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
stateDiagram-v2
  [*] --> open : created by agent
  open --> in_progress : staff picks it up
  in_progress --> resolved : staff resolves
  in_progress --> open : student replies (re-opens triage)
  resolved --> closed : auto-close after N days
  resolved --> in_progress : student re-replies
  closed --> [*]
```

---

## Data flow diagram

Where every kind of data physically lives and how it moves.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
flowchart LR
  U[Student<br/>plain English] -- HTTPS+JWT --> CH[/chat endpoint/]
  CH -- question + student_id --> G[LangGraph state]
  G -- system prompts --> LLM[NVIDIA NIM]
  LLM -- tool_calls --> G
  G -- typed args --> T[Tool functions]
  T -- SELECT --> SQL[(SQLite)]
  SQL -- rows --> T
  T -- JSON --> G
  G -- chat history --> SQL
  G -- tickets --> SQL
  G -- final answer --> CH
  CH -- JSON --> U

  classDef io fill:#E8F1FF,stroke:#111111,color:#111111
  classDef proc fill:#E8FFEF,stroke:#111111,color:#111111
  classDef store fill:#F5E8FF,stroke:#111111,color:#111111
  class U,CH io
  class G,T,LLM proc
  class SQL store
```

---

## Deployment diagram

Everything is local. Two processes, one external service.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
flowchart TB
  subgraph laptop["Developer laptop (Windows)"]
    direction TB
    subgraph py["Python venv"]
      uvicorn[uvicorn :8000<br/>FastAPI app]
      sqlite[(university_mock.db<br/>SQLite file)]
      uvicorn --- sqlite
    end
    subgraph emul["Android emulator (Pixel 6 API 34)"]
      apk[com.example.final_project<br/>debug APK]
    end
    apk -- "http://10.0.2.2:8000" --> uvicorn
  end

  cloud[(NVIDIA NIM cloud<br/>openai/gpt-oss-120b<br/>OpenAI-compatible)]
  uvicorn -- HTTPS --> cloud

  classDef laptop fill:#E8F1FF,stroke:#111111,color:#111111
  classDef py fill:#FFF4E0,stroke:#111111,color:#111111
  classDef store fill:#F5E8FF,stroke:#111111,color:#111111
  class uvicorn,apk laptop
  class py py
  class sqlite,cloud store
```

---

## Android navigation

The five Compose screens and how the user moves between them.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
stateDiagram-v2
  [*] --> Login : token missing
  [*] --> Home  : token present
  Login --> Home : success
  Login --> Signup : "Sign up"
  Signup --> Home : success
  Signup --> Login : "Sign in"
  Home --> Chat : "Ask the assistant"
  Home --> Tickets : "My tickets"
  Home --> Login : "Sign out"
  Chat --> TicketDetail : tap "View ticket #N"
  Tickets --> TicketDetail : tap a card
  TicketDetail --> Chat : back
  TicketDetail --> Tickets : back
  Chat --> Home : back
  Tickets --> Home : back
```

---

## Authentication flow

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
sequenceDiagram
  autonumber
  actor Student
  participant App
  participant Auth as /auth/login
  participant Sec as security.py
  participant DB
  participant Any as any protected endpoint

  Student->>App: email + password
  App->>Auth: POST {email, password}
  Auth->>DB: SELECT student WHERE email=?
  DB-->>Auth: row + bcrypt hash
  Auth->>Sec: verify_password(plain, hash)
  Sec-->>Auth: ok
  Auth->>Sec: create_access_token(student.id)
  Sec-->>Auth: JWT (HS256, exp=24h)
  Auth-->>App: {access_token, student_id, name, email}
  App->>App: DataStore.save(token)
  Note over App: subsequent requests
  App->>Any: Authorization: Bearer <token>
  Any->>Sec: get_current_student
  Sec->>Sec: jwt.decode
  Sec->>DB: SELECT student WHERE id=sub
  DB-->>Sec: Student row
  Sec-->>Any: current student
  Any-->>App: response
```

A **tampered or expired token** never reaches the database — `jwt.decode` raises before `get_current_student` resolves a row, and FastAPI returns `401 Unauthorized`.

---

## Tool calling cycle (inside one dept agent)

Zoom in on what happens during a single department agent's React loop. This is **the** moment where the LLM "decides" to read a row from the DB.

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Inter, sans-serif','primaryTextColor':'#111111','lineColor':'#111111','primaryBorderColor':'#111111'}}}%%
sequenceDiagram
  autonumber
  participant Sub as Dept sub-graph
  participant LLM as ChatOpenAI<br/>(bind_tools)
  participant TN as ToolNode
  participant Py as Python tool fn
  participant DB

  Sub->>LLM: messages + tool schemas
  LLM-->>Sub: assistant message with tool_calls=[reg_check_enrollment_eligibility(course_code='CS301')]
  Sub->>TN: route to tools (conditional edge)
  TN->>Py: reg_check_enrollment_eligibility(db, student_id, 'CS301')
  Py->>DB: SELECT course / holds / prereqs / grades
  DB-->>Py: rows
  Py-->>TN: dict result
  TN-->>Sub: ToolMessage(content=JSON)
  Sub->>LLM: messages now include the tool result
  LLM-->>Sub: assistant message (no more tool_calls)
  Note over Sub: loop ends — last message is the answer<br/>(may contain <ESCALATE>{...}</ESCALATE>)
```

---

_Last updated: post-LangGraph-rewrite, 30/30 functional + 25/25 security + 5/5 UI green._
