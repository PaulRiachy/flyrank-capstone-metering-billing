import json
from contextlib import asynccontextmanager
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import Base, SessionLocal, engine, get_db
from app.metering import month_start, next_month_start, record_generation, refresh_usage_rollup
from app.models import Plan, Subscription, Tenant, UsageEvent, UsageRollup, WebhookEvent
from app.payment import MockStripeProvider
from app.pricing import estimate_cost_cents
from app.schemas import CheckoutRequest, CheckoutResponse, GenerateRequest, GenerateResponse, TenantCreate, TenantOut, UsageResponse

provider = MockStripeProvider()

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_plans(db)
    finally:
        db.close()
    yield

app = FastAPI(title="Usage Metering & Billing Engine", lifespan=lifespan)

def seed_plans(db: Session):
    if db.execute(select(Plan)).scalars().first():
        return
    db.add_all([
        Plan(name="free", api_call_limit=1000, ai_token_limit=100000, api_call_price_cents=1, input_token_microcents=10, cached_input_microcents=2, output_token_microcents=20),
        Plan(name="pro", api_call_limit=10000, ai_token_limit=1000000, api_call_price_cents=1, input_token_microcents=10, cached_input_microcents=2, output_token_microcents=20),
    ])
    db.commit()


def run_rollup_job(tenant_id: int):
    with SessionLocal() as db:
        refresh_usage_rollup(db, tenant_id)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tenants", response_model=TenantOut)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)):
    plan = db.execute(select(Plan).where(Plan.name == "free")).scalar_one()
    tenant = Tenant(name=payload.name, plan_id=plan.id)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return TenantOut(id=tenant.id, name=tenant.name, plan=tenant.plan.name, subscription_status=tenant.subscription_status)


@app.get("/tenants/{tenant_id}", response_model=TenantOut)
def get_tenant(tenant_id: int, db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant not found")
    return TenantOut(id=tenant.id, name=tenant.name, plan=tenant.plan.name, subscription_status=tenant.subscription_status)


@app.post("/generate", response_model=GenerateResponse)
def generate(payload: GenerateRequest, background_tasks: BackgroundTasks, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), db: Session = Depends(get_db)):
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header is required")
    tenant = db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant not found")
    if tenant.subscription_status != "active":
        raise HTTPException(402, "subscription is not active")
    try:
        event, cost = record_generation(db, payload.tenant_id, idempotency_key, payload.api_calls, payload.input_tokens, payload.cached_input_tokens, payload.output_tokens, payload.reasoning_tokens)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except PermissionError as exc:
        raise HTTPException(429, str(exc))
    background_tasks.add_task(run_rollup_job, payload.tenant_id)
    return GenerateResponse(event_id=event.id, api_calls_added=event.api_calls, ai_tokens_added=event.ai_tokens, estimated_cost_cents=cost)


@app.get("/tenants/{tenant_id}/usage", response_model=UsageResponse)
def usage(tenant_id: int, db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant not found")
    start, end = month_start(), next_month_start()
    events = db.execute(select(UsageEvent).where(UsageEvent.tenant_id == tenant_id, UsageEvent.created_at >= start, UsageEvent.created_at < end)).scalars().all()
    api_used = sum(e.api_calls for e in events)
    token_used = sum(e.ai_tokens for e in events)
    cost = sum(estimate_cost_cents(e.api_calls, e.input_tokens, e.cached_input_tokens, e.output_tokens, e.reasoning_tokens, api_call_cents=tenant.plan.api_call_price_cents, input_microcents=tenant.plan.input_token_microcents, cached_microcents=tenant.plan.cached_input_microcents, output_microcents=tenant.plan.output_token_microcents) for e in events)
    return UsageResponse(tenant_id=tenant_id, month=start.strftime("%Y-%m"), api_calls_used=api_used, api_calls_limit=tenant.plan.api_call_limit, ai_tokens_used=token_used, ai_tokens_limit=tenant.plan.ai_token_limit, estimated_cost_cents=cost)


@app.get("/tenants/{tenant_id}/usage/rollup")
def usage_rollup(tenant_id: int, db: Session = Depends(get_db)):
    rollup = db.execute(select(UsageRollup).where(UsageRollup.tenant_id == tenant_id, UsageRollup.month == month_start().strftime("%Y-%m"))).scalar_one_or_none()
    if not rollup:
        raise HTTPException(404, "rollup not found")
    return {"tenant_id": tenant_id, "month": rollup.month, "api_calls_used": rollup.api_calls_used, "ai_tokens_used": rollup.ai_tokens_used, "estimated_cost_cents": rollup.estimated_cost_cents}


@app.post("/billing/checkout", response_model=CheckoutResponse)
def checkout(payload: CheckoutRequest, db: Session = Depends(get_db)):
    tenant = db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant not found")
    session = provider.create_checkout_session(tenant.id)
    tenant.stripe_customer_id = session.stripe_customer_id
    db.commit()
    return CheckoutResponse(session_id=session.session_id, checkout_url=session.checkout_url)


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(None, alias="Stripe-Signature"), db: Session = Depends(get_db)):
    payload = await request.body()
    if not stripe_signature or not provider.verify_signature(payload, stripe_signature):
        raise HTTPException(400, "invalid webhook signature")
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(400, "invalid webhook payload")
    event_id, event_type, data = event.get("id"), event.get("type"), event.get("data", {})
    if not event_id or not event_type:
        raise HTTPException(400, "invalid webhook event")
    if db.execute(select(WebhookEvent).where(WebhookEvent.stripe_event_id == event_id)).scalar_one_or_none():
        return {"status": "duplicate"}
    tenant = db.get(Tenant, data.get("tenant_id"))
    if not tenant:
        raise HTTPException(404, "tenant not found")
    if event_type not in {"checkout.session.completed", "customer.subscription.updated", "customer.subscription.deleted"}:
        db.add(WebhookEvent(stripe_event_id=event_id, event_type=event_type))
        db.commit()
        return {"status": "ignored"}
    plan_name = data.get("plan_name", "pro")
    plan = db.execute(select(Plan).where(Plan.name == plan_name)).scalar_one_or_none()
    if not plan:
        raise HTTPException(400, "unknown plan")
    tenant.plan_id = plan.id
    tenant.subscription_status = "canceled" if event_type == "customer.subscription.deleted" else data.get("status", "active")
    subscription = db.execute(select(Subscription).where(Subscription.tenant_id == tenant.id)).scalar_one_or_none()
    if subscription:
        subscription.stripe_subscription_id = data.get("stripe_subscription_id", subscription.stripe_subscription_id)
        subscription.status = tenant.subscription_status
        subscription.plan_name = plan.name
    else:
        db.add(Subscription(tenant_id=tenant.id, stripe_subscription_id=data.get("stripe_subscription_id", f"sub_{event_id}"), status=tenant.subscription_status, plan_name=plan.name))
    db.add(WebhookEvent(stripe_event_id=event_id, event_type=event_type))
    db.commit()
    return {"status": "processed"}
