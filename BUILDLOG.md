# Build Log

## Baseline

The Python/FastAPI implementation was supplied as a working starter and verified with automated tests.

## Hardening pass

- Replaced the usage-event idempotency constraint with a dedicated persistent idempotency record so one request can contain both API calls and AI tokens.
- Added monthly usage rollups.
- Added a FastAPI background job that refreshes the current-month rollup after successful metering.
- Added a pricing consistency test.
- Added a combined API-call and token idempotency test.
- Expanded the manual acceptance checklist.

## Payment boundary

Stripe interactions remain mocked as requested. The repository does not claim real Stripe test-mode verification.
