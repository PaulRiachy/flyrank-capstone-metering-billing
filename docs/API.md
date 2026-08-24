# API

Start the API with `uvicorn app.main:app --reload` and use `/docs`.

Create tenant:
`POST /tenants` with `{"name":"Acme"}`

Meter usage with `Idempotency-Key`:
`POST /generate`

Read monthly usage:
`GET /tenants/{tenant_id}/usage`

Create mock checkout:
`POST /billing/checkout`

Post signed mock payment events:
`POST /webhooks/stripe`
