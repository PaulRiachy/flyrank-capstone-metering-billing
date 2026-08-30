# Usage Metering & Billing Engine

Python/FastAPI implementation of the capstone scope with SQLite and a mocked Stripe provider.

## Setup

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python -m app.seed
```

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
python -m app.seed
```

## Test

```bash
pytest -q
```

Expected result: `15 passed`.

## Run

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs.

## Docker

```bash
docker compose up --build
```

## Manual acceptance flow

1. Create a tenant with `POST /tenants`.
2. Call `POST /generate` with `Idempotency-Key: req-1`.
3. Repeat the identical request and verify the same `event_id` and unchanged usage.
4. Send 1000 API calls for a Free tenant and verify the request succeeds.
5. Send one more API call and verify HTTP 429.
6. Read `/tenants/{id}/usage` and `/tenants/{id}/usage/rollup`.
7. Create a mock checkout with `POST /billing/checkout`.
8. Build and sign a mock webhook using `MockStripeProvider`.
9. Post it to `/webhooks/stripe` and verify the tenant becomes Pro.
10. Replay it and verify `duplicate`.
11. Change the signature and verify HTTP 400.

## Architecture

```text
Client -> FastAPI -> Metering -> SQLite
                    |
                    +-> idempotency
                    +-> quota
                    +-> pricing
                    +-> background rollup

Mock Stripe -> signed webhook -> verify -> dedupe -> subscription sync
```

## Scope and limitation

The implementation intentionally uses a mocked payment provider for deterministic learning and tests. It does not claim to be a real Stripe integration. 

