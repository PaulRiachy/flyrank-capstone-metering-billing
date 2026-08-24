# Design

## Metering

`POST /generate` validates the tenant and idempotency key, reserves the idempotency key in the same transaction as the usage decision, checks the current UTC calendar-month quota, persists the usage event, and commits.

## Idempotency

`IdempotencyRecord` has a database uniqueness constraint on `(tenant_id, idempotency_key)`. This lets one request record both API-call and AI-token quantities without duplicating the request.

## Quotas

Free is 1000 API calls and 100000 AI tokens per UTC calendar month. Pro is 10000 API calls and 1000000 AI tokens. Rejected requests roll back their idempotency reservation and create no usage event.

## Pricing

Money is represented as integer cents and token prices as integer microcents. Cached input is priced separately from fresh input. Reasoning tokens use output pricing.

## Background job

After successful metering, FastAPI schedules a background task that rebuilds the tenant's current-month usage rollup. The rollup is persisted and exposed through `/tenants/{tenant_id}/usage/rollup`.

## Payments

`MockStripeProvider` isolates checkout and webhook behavior from the application. Webhook signatures use HMAC-SHA256 and webhook event IDs are persisted for replay protection.

## Tenant isolation

Every usage and idempotency query is scoped by tenant ID.
