def tenant(client, name="Acme"):
    response = client.post("/tenants", json={"name": name})
    assert response.status_code == 200
    return response.json()

def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}

def test_create_tenant(client):
    t = tenant(client)
    assert t["plan"] == "free"
    assert t["subscription_status"] == "active"

def test_idempotency_with_api_and_tokens(client):
    t = tenant(client)
    payload = {"tenant_id": t["id"], "api_calls": 1, "input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30, "reasoning_tokens": 10}
    headers = {"Idempotency-Key": "req-1"}
    a = client.post("/generate", json=payload, headers=headers)
    b = client.post("/generate", json=payload, headers=headers)
    assert a.status_code == b.status_code == 200
    assert a.json()["event_id"] == b.json()["event_id"]
    usage = client.get(f"/tenants/{t['id']}/usage").json()
    assert usage["api_calls_used"] == 1
    assert usage["ai_tokens_used"] == 140

def test_quota_exact_boundary(client):
    t = tenant(client)
    ok = client.post("/generate", json={"tenant_id": t["id"], "api_calls": 1000}, headers={"Idempotency-Key": "limit"})
    blocked = client.post("/generate", json={"tenant_id": t["id"], "api_calls": 1}, headers={"Idempotency-Key": "over"})
    assert ok.status_code == 200
    assert blocked.status_code == 429

def test_rejected_request_records_no_usage(client):
    t = tenant(client)
    response = client.post("/generate", json={"tenant_id": t["id"], "api_calls": 1001}, headers={"Idempotency-Key": "bad"})
    assert response.status_code == 429
    assert client.get(f"/tenants/{t['id']}/usage").json()["api_calls_used"] == 0

def test_isolation(client):
    a, b = tenant(client, "A"), tenant(client, "B")
    client.post("/generate", json={"tenant_id": a["id"], "api_calls": 3}, headers={"Idempotency-Key": "a"})
    client.post("/generate", json={"tenant_id": b["id"], "api_calls": 7}, headers={"Idempotency-Key": "b"})
    assert client.get(f"/tenants/{a['id']}/usage").json()["api_calls_used"] == 3
    assert client.get(f"/tenants/{b['id']}/usage").json()["api_calls_used"] == 7

def test_background_rollup_matches_usage(client):
    t = tenant(client)
    client.post("/generate", json={"tenant_id": t["id"], "api_calls": 4, "input_tokens": 100}, headers={"Idempotency-Key": "rollup"})
    usage = client.get(f"/tenants/{t['id']}/usage").json()
    rollup = client.get(f"/tenants/{t['id']}/usage/rollup").json()
    assert rollup["api_calls_used"] == usage["api_calls_used"] == 4
    assert rollup["ai_tokens_used"] == usage["ai_tokens_used"] == 100
    assert rollup["estimated_cost_cents"] == usage["estimated_cost_cents"]
