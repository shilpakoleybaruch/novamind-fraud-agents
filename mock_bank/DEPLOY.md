# Deploying Mock Bank API to IBM Cloud Code Engine

> **Do not run these commands yet.** This file documents the exact steps for when you are ready to deploy.
>
> Build context is the `novamind/` directory. All commands are run from there.
> No Docker, no Container Registry required — Code Engine builds from source.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| IBM Cloud CLI | `ibmcloud` installed and logged in (`ibmcloud login --sso`) |
| Code Engine plugin | `ibmcloud plugin install code-engine` |
| No Docker or Container Registry needed | Build runs entirely on Code Engine |

---

## Complete command list (run in order from `novamind/`)

**1. Log in to IBM Cloud:**
```bash
ibmcloud login --sso
```

**2. List resource groups and target eu-de:**
```bash
ibmcloud resource groups
ibmcloud target -r eu-de -g Default
```
*(Replace `Default` with your resource group name if different.)*

**3. Create the Code Engine project:**
```bash
ibmcloud ce project create --name novamind
```
*(If it already exists: `ibmcloud ce project select --name novamind`)*

**4. Generate a random API key and store it as a Code Engine secret:**
```bash
API_KEY=$(openssl rand -hex 32)
echo "MOCK_BANK_API_KEY=${API_KEY}"
ibmcloud ce secret create \
  --name mock-bank-api-key \
  --from-literal MOCK_BANK_API_KEY=${API_KEY}
```
*(Copy the printed key — you will need it in step 8.)*

**5. Create and deploy the app from source (run from `novamind/`):**
```bash
ibmcloud ce app create \
  --name mock-bank \
  --build-source . \
  --build-dockerfile mock_bank/Dockerfile \
  --build-strategy dockerfile \
  --build-size medium \
  --port 8080 \
  --min-scale 0 \
  --max-scale 1 \
  --cpu 0.25 \
  --memory 0.5G \
  --env-from-secret mock-bank-api-key \
  --env ENABLE_TEST_ENDPOINTS=true
```

**6. Get the app URL:**
```bash
APP_URL=$(ibmcloud ce app get --name mock-bank --output url)
echo "APP_URL=${APP_URL}"
```

**7. Set BASE_URL on the running app:**
```bash
ibmcloud ce app update \
  --name mock-bank \
  --env BASE_URL=${APP_URL}
```

**8. Update the Orchestrate connection credentials:**
```bash
orchestrate connections set-credentials --app-id novamind_mock_bank
```
*(When prompted: `MOCK_BANK_URL` → paste `APP_URL` from step 6; `MOCK_BANK_API_KEY` → paste the key from step 4.)*

**9. Verify:**
```bash
APP_URL=$(ibmcloud ce app get --name mock-bank --output url)
curl "${APP_URL}/docs"
curl -H "X-API-Key: ${API_KEY}" "${APP_URL}/customers/C-DANA-001/transactions?days=7"
```

**10. Redeploy after code changes (run from `novamind/`):**
```bash
ibmcloud ce app update \
  --name mock-bank \
  --build-source . \
  --build-dockerfile mock_bank/Dockerfile \
  --build-strategy dockerfile \
  --build-size medium
```

**11. Tear down:**
```bash
ibmcloud ce app delete    --name mock-bank         --force
ibmcloud ce secret delete --name mock-bank-api-key --force
ibmcloud ce project delete --name novamind         --force
```

---

## Environment variables reference

| Variable | Required | Description |
|---|---|---|
| `MOCK_BANK_API_KEY` | **Yes** | Injected from the `mock-bank-api-key` secret. Used as the `X-API-Key` value on all API endpoints. |
| `BASE_URL` | Yes | Public HTTPS URL of this app (set in step 7). Used in case-view and question-screen page links. |
| `ENABLE_TEST_ENDPOINTS` | **Demo only** | Set `true` to enable `POST /questions/{id}/simulate-reply` for the scenario runner. **Must be `false` or unset in any non-demo deployment.** |
| `DATABASE_URL` | No | SQLAlchemy URL. Defaults to `sqlite:////data/mock_bank.db`. Reseeded from `/seed_data/` on every cold start. |
| `SEED_DATA_DIR` | No | Path to seed JSON files. Defaults to `/seed_data` in the image. |
| `PORT` | No | Port to listen on. Code Engine injects this automatically; default `8080`. |
