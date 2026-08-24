import pytest
from app.pricing import billable_token_counts, estimate_cost_cents

def test_token_categories():
    assert billable_token_counts(1000, 400, 200, 100) == (600, 400, 300)

def test_reasoning_is_output():
    assert billable_token_counts(100, 0, 50, 25) == (100, 0, 75)

def test_cached_cannot_exceed_input():
    with pytest.raises(ValueError):
        billable_token_counts(10, 11, 0, 0)

def test_cost_uses_integer_cents():
    assert estimate_cost_cents(100, 1000, 400, 200, 100) == 101
    assert isinstance(estimate_cost_cents(1, 1, 0, 0, 0), int)

def test_usage_cost_matches_metered_response(client):
    tenant = client.post("/tenants", json={"name": "Acme"}).json()
    response = client.post("/generate", json={"tenant_id": tenant["id"], "api_calls": 2, "input_tokens": 1000, "cached_input_tokens": 400, "output_tokens": 200, "reasoning_tokens": 100}, headers={"Idempotency-Key": "price"})
    usage = client.get(f"/tenants/{tenant['id']}/usage").json()
    assert response.json()["estimated_cost_cents"] == usage["estimated_cost_cents"]
