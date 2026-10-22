# Novamind — IBM SkillsBuild Prototype

Multi-agent fraud triage system built with the watsonx Orchestrate ADK.

See [`docs/BRIEF.md`](docs/BRIEF.md) for the full project brief and ground truth.

---

## Prerequisites

| Tool | Where needed |
|---|---|
| Python ≥ 3.12 | Tests (local) |
| `pip install pytest httpx fastapi "uvicorn[standard]" sqlalchemy python-multipart` | Tests (local) |
| `uv` (optional) | Running tests via `uv run` instead of a bare `python3 -m pytest` |
| `ibm-watsonx-orchestrate` CLI (`orchestrate`) | ☁️ IBM Cloud steps only |
| IBM Cloud account + Code Engine project | ☁️ IBM Cloud steps only |

Steps labelled **☁️ IBM Cloud** require an active IBM Cloud account and a provisioned Orchestrate environment (`mycloud`). All other steps run fully locally.

---

## Quick start

### 1. Run the tests locally (no cloud account needed)

```bash
# Scenario tests — pure Python, no server required
python3 -m pytest tests/test_scenarios.py -v

# Guardrail tests — spins up FastAPI in-process via TestClient, no server required
ENABLE_TEST_ENDPOINTS=true python3 -m pytest mock_bank/tests/test_guardrails.py -v
```

### 2. Run the mock bank locally (optional — for manual exploration)

```bash
# Install mock bank dependencies
pip install -r mock_bank/requirements.txt

# Start the server
MOCK_BANK_API_KEY=dev-secret \
ENABLE_TEST_ENDPOINTS=true \
BASE_URL=http://localhost:8000 \
uvicorn mock_bank.main:app --reload --port 8000
```

The API docs are at <http://localhost:8000/docs>.

### 3. ☁️ Deploy the mock bank to IBM Cloud Code Engine

See [`mock_bank/DEPLOY.md`](mock_bank/DEPLOY.md) for the full step-by-step commands.
The short version:

```bash
ibmcloud login --sso
ibmcloud ce project create --name novamind  # or select if already exists

# Build and deploy from repo root
API_KEY=$(openssl rand -hex 32)
ibmcloud ce secret create --name mock-bank-api-key \
  --from-literal MOCK_BANK_API_KEY=${API_KEY}

ibmcloud ce app create \
  --name mock-bank \
  --build-source . \
  --build-dockerfile mock_bank/Dockerfile \
  --build-strategy dockerfile \
  --build-size medium \
  --port 8080 --min-scale 0 --max-scale 1 \
  --env-from-secret mock-bank-api-key \
  --env ENABLE_TEST_ENDPOINTS=true

APP_URL=$(ibmcloud ce app get --name mock-bank --output url)
ibmcloud ce app update --name mock-bank --env BASE_URL=${APP_URL}
```

### 4. ☁️ Import everything into Orchestrate

```bash
# Activate the target environment first
orchestrate env activate mycloud

# Import connection, tools, knowledge base, agents (in the correct order)
./scripts/import_all.sh
```

`import_all.sh` enforces the mandatory import order:
connection → tools → knowledge base → leaf agents → `risk_agent` (supervisor).

After import, set the connection credentials when prompted:

```bash
orchestrate connections set-credentials --app-id novamind_mock_bank
# MOCK_BANK_URL  → paste the APP_URL from the Code Engine step
# MOCK_BANK_API_KEY → paste the API_KEY from the Code Engine step
```

---

## Teardown

### Local

```bash
# Nothing to tear down — tests use an in-memory/temp SQLite file
# If you started the server manually:
# Ctrl-C to stop uvicorn, then delete the SQLite file if created:
rm -f mock_bank/mock_bank.db
```

### ☁️ Orchestrate (remove all imported assets)

```bash
./scripts/remove_all.sh
```

### ☁️ IBM Cloud Code Engine (remove the deployed mock bank)

```bash
ibmcloud ce app delete    --name mock-bank          --force
ibmcloud ce secret delete --name mock-bank-api-key  --force
# Optionally delete the whole project:
ibmcloud ce project delete --name novamind          --force
```
## Known limitations of the local test runner
- It tests the deterministic layer (scoring, baseline, API guardrails), not the
  Granite agents. Agent behaviour is tested in the Orchestrate chat.
- Latency excludes LLM calls.
- S2: a moderate transaction is pending while Dana is asked, so no hold exists
  and the release endpoint isn't called. The release guardrail is covered in
  mock_bank/tests/test_guardrails.py.
- S7 scores above 30, so it would ask even without the thin-baseline rule.
  The lowered threshold (20) is covered by unit tests only
  