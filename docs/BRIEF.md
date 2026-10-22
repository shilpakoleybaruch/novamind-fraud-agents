# Project Novamind — Ground-Truth Brief

> **Status:** Ground truth. Do not edit without team sign-off.

---

## Problem

Banks catch suspicious card activity with generic rules and then freeze the whole account with no explanation. Our user, **Dana Reyes**, is a 38-year-old sole-proprietor shop owner with one business account and one card that pays suppliers, rent, and herself. She can't tell a real fraud text from a scam, so she never taps alert links. A blocked card means she misses a supplier payment.

---

## Solution

A multi-agent system that knows Dana's normal spending, decides how much friction each transaction deserves, asks her one verifiable question inside her banking app (no links), and acts on her answer with a **partial hold** instead of a full freeze.

---

## Four Agents (one job each)

| Agent | Role | Key constraint |
|---|---|---|
| `baseline_agent` | Builds Dana's normal pattern (merchants, weekday/time, amounts, volumes) and answers "is this consistent with who this customer is?" | Read-only. No account write access. |
| `risk_agent` | **SUPERVISOR.** Scores the deviation and decides the response: allow, ask, partially restrict, or escalate to a human analyst. Retrieves scam patterns and bank policy (RAG) before scoring. | Orchestrates all other agents. |
| `engagement_agent` | Writes and sends Dana one plain-language in-app question and reads her reply. | **No account access.** Question may only use details from Dana's own history. No links. Never details a scammer could look up. |
| `action_agent` | Places or releases the partial hold and updates the case. | **ONLY agent with account write access.** Acts only on a `risk_agent` authorization. Release tool enforces verified-answer check in code, not just in prompts. |

---

## Workflow

```
Transaction → baseline check → risk score
```

| Score | Branch |
|---|---|
| < 30 (Low) | Clear the payment silently. |
| 30–69 (Moderate) | Ask Dana in-app via `engagement_agent`. |
| ≥ 70 (High) | Partial hold, open a case, queue an analyst. |

### Moderate branch outcomes

- **"That was me" (verified):** release hold, add merchant to baseline.
- **"Not me":** partial hold on suspicious activity only, open a case.

### Edge rules

1. **Rapid approvals:** 3 or more "That was me" approvals within 24 hours → escalate to analyst instead of releasing.
2. **No reply in 15 minutes:** retry on a second channel (simulated push notification), then keep the hold and queue an analyst.
3. **Thin baseline:** fewer than 30 transactions OR under 60 days of history → lower the ask threshold to 20 (ask more, guess less).
4. **Tool failure or conflicting signals:** escalate. Never release anything unverified.

---

## Non-Negotiable Rules

1. **Nothing ever releases a hold without Dana's verified answer.** Enforce this in the release tool's code, not just in prompts.
2. **Only `action_agent`** gets tools that change account state (hold, release, case writes).
3. **`engagement_agent`'s question** may only use details from Dana's own history (e.g. "you usually shop there on Tuesdays"), never details a scammer could look up, and never a link.
4. **The risk score uses behaviour vs. Dana's own baseline only.** No age, gender, ethnicity, neighbourhood, or name.
5. **Partial hold, not a full freeze:** essential payees (supplier payments and rent transfer) keep working.
6. **Every decision is logged:** signals, score, branch, which agent acted, timestamp, reason text.
7. **Plain, calm wording.** No scare tactics.

---

## Prototype Scope

- Synthetic data only, one customer (Dana). Core banking and the payment rail are simulated.
- State lives in a small mock bank API (**FastAPI + SQLite**) deployed to **IBM Cloud Code Engine**. Orchestrate Python tools call it over HTTPS using an Orchestrate connection for the base URL and API key.
- The mock API also serves two prototype pages: Dana's in-app question screen and the live case view.

---

## Tech Stack

- **watsonx Orchestrate ADK** — Python tools with the `@tool` decorator, agent YAML specs, a knowledge base for RAG, deployed to cloud environment `mycloud`.
- **LLM:** Granite model from watsonx.ai (fall back if tool-calling proves unreliable).
- **Mock bank:** FastAPI + SQLite, Dockerfile, seed data, two HTML pages.
- **ADK CLI:** `orchestrate` (package: `ibm-watsonx-orchestrate`, installed via `uv`).

---

## Project Layout

```
novamind/
  docs/BRIEF.md                   ← this file
  mock_bank/                      FastAPI app, SQLite, seed data, Dockerfile, HTML pages
  data/                           synthetic transactions + scenarios (JSON)
  tools/                          Orchestrate Python tools, one file per agent
  agents/                         agent YAML specs
  knowledge/                      policy + scam-pattern documents and knowledge base spec
  connections/                    connection spec for the mock bank API
  tests/                          scenario runner
  scripts/import_all.sh           import everything into the active env
  scripts/remove_all.sh           tear everything down from the active env
  README.md
```

---

## ADK Import Commands (confirmed from CLI)

### Tools
```bash
orchestrate tools import --kind python --file tools/<agent>_tools.py \
  --requirements-file tools/requirements.txt \
  --app-id mock-bank-connection
```

### Knowledge base
```bash
orchestrate knowledge-bases import --file knowledge/novamind_kb.yaml \
  --app-id mock-bank-connection   # only if using an external vector index
```

### Connection
```bash
orchestrate connections import --file connections/mock_bank.yaml
# then set credentials:
orchestrate connections set-credentials --app-id mock-bank-connection
```

### Agents
```bash
orchestrate agents import --file agents/<agent_name>.yaml
```

### Teardown
```bash
orchestrate agents remove --name <agent_name> --kind native
orchestrate tools remove --name <tool_name>
orchestrate knowledge-bases remove --name novamind-kb
orchestrate connections remove --app-id mock-bank-connection
```

---

## Gap Analysis & Resolution

Gaps identified during initial analysis — all **resolved in later steps**, do not treat as open issues.

| # | Gap | Resolved in |
|---|-----|-------------|
| 1 | **Payment verification + 3-approval rule** — no enforcement of the three-approval gate before a payment is executed | Prompt 2 (mock bank API) |
| 2 | **`essential_payees` list** — synthetic customer data contained no `essential_payees` field, leaving the baseline agent without the data it needs to distinguish protected payees | Prompt 1 (synthetic data) |
| 3 | **Native supervisor with collaborators** — the `risk_agent` spec lacked the `kind: native` declaration and the `collaborators` list required to act as the multi-agent supervisor | Prompt 8 (risk_agent spec) |
| 4 | **Second-channel retry endpoint** — no fallback communication channel was defined for retrying failed engagement actions | Prompt 2 (mock bank API) |
| 5 | **Approval-count tracking** — no mechanism to accumulate and persist the rolling approval count across agent turns | Prompt 2 (mock bank API) |
