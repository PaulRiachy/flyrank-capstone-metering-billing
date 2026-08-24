from app.payment import MockStripeProvider
from app.db import SessionLocal
from app.models import Tenant

def tenant(client):
    return client.post("/tenants", json={"name": "Acme"}).json()

def signed(client, event_id, tenant_id):
    provider = MockStripeProvider()
    payload = provider.build_event(event_id, "checkout.session.completed", tenant_id, "pro", "active", f"sub_{event_id}")
    return payload, provider.sign_event(payload)

def test_checkout(client):
    t = tenant(client)
    response = client.post("/billing/checkout", json={"tenant_id": t["id"]})
    assert response.status_code == 200
    assert response.json()["session_id"].startswith("cs_test_")

def test_signed_webhook_upgrades(client):
    t = tenant(client)
    payload, signature = signed(client, "evt_1", t["id"])
    response = client.post("/webhooks/stripe", content=payload, headers={"Stripe-Signature": signature})
    assert response.json() == {"status": "processed"}
    with SessionLocal() as db:
        assert db.get(Tenant, t["id"]).plan.name == "pro"

def test_bad_signature(client):
    t = tenant(client)
    payload, _ = signed(client, "evt_bad", t["id"])
    assert client.post("/webhooks/stripe", content=payload, headers={"Stripe-Signature": "bad"}).status_code == 400

def test_webhook_replay(client):
    t = tenant(client)
    payload, signature = signed(client, "evt_replay", t["id"])
    first = client.post("/webhooks/stripe", content=payload, headers={"Stripe-Signature": signature})
    second = client.post("/webhooks/stripe", content=payload, headers={"Stripe-Signature": signature})
    assert first.json()["status"] == "processed"
    assert second.json()["status"] == "duplicate"
