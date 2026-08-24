from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import IdempotencyRecord, Tenant, UsageEvent, UsageRollup
from app.pricing import estimate_cost_cents

def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

def next_month_start(now: datetime | None = None) -> datetime:
    start = month_start(now)
    if start.month == 12:
        return start.replace(year=start.year + 1, month=1)
    return start.replace(month=start.month + 1)

def current_usage(db: Session, tenant_id: int, now: datetime | None = None) -> tuple[int, int]:
    start, end = month_start(now), next_month_start(now)
    row = db.execute(
        select(
            func.coalesce(func.sum(UsageEvent.api_calls), 0),
            func.coalesce(func.sum(UsageEvent.ai_tokens), 0),
        ).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.created_at >= start,
            UsageEvent.created_at < end,
        )
    ).one()
    return int(row[0]), int(row[1])

def record_generation(db: Session, tenant_id: int, key: str, api_calls: int, input_tokens: int, cached_input_tokens: int, output_tokens: int, reasoning_tokens: int):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise ValueError("tenant not found")
    if cached_input_tokens > input_tokens:
        raise ValueError("cached input tokens cannot exceed input tokens")

    existing_key = db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == tenant_id,
            IdempotencyRecord.idempotency_key == key,
        )
    ).scalar_one_or_none()
    if existing_key:
        event = db.execute(
            select(UsageEvent).where(
                UsageEvent.tenant_id == tenant_id,
                UsageEvent.idempotency_key == key,
            )
        ).scalar_one()
        return event, estimate_cost_cents(event.api_calls, event.input_tokens, event.cached_input_tokens, event.output_tokens, event.reasoning_tokens, api_call_cents=tenant.plan.api_call_price_cents, input_microcents=tenant.plan.input_token_microcents, cached_microcents=tenant.plan.cached_input_microcents, output_microcents=tenant.plan.output_token_microcents)

    try:
        db.add(IdempotencyRecord(tenant_id=tenant_id, idempotency_key=key))
        db.flush()
    except IntegrityError:
        db.rollback()
        event = db.execute(select(UsageEvent).where(UsageEvent.tenant_id == tenant_id, UsageEvent.idempotency_key == key)).scalar_one()
        return event, estimate_cost_cents(event.api_calls, event.input_tokens, event.cached_input_tokens, event.output_tokens, event.reasoning_tokens, api_call_cents=tenant.plan.api_call_price_cents, input_microcents=tenant.plan.input_token_microcents, cached_microcents=tenant.plan.cached_input_microcents, output_microcents=tenant.plan.output_token_microcents)

    ai_tokens = input_tokens + output_tokens + reasoning_tokens
    api_used, token_used = current_usage(db, tenant_id)
    if api_used + api_calls > tenant.plan.api_call_limit:
        db.rollback()
        raise PermissionError(f"api_call quota exceeded: used={api_used}, requested={api_calls}, limit={tenant.plan.api_call_limit}")
    if token_used + ai_tokens > tenant.plan.ai_token_limit:
        db.rollback()
        raise PermissionError(f"ai_token quota exceeded: used={token_used}, requested={ai_tokens}, limit={tenant.plan.ai_token_limit}")

    event = UsageEvent(
        tenant_id=tenant_id,
        api_calls=api_calls,
        ai_tokens=ai_tokens,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        idempotency_key=key,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    cost = estimate_cost_cents(api_calls, input_tokens, cached_input_tokens, output_tokens, reasoning_tokens, api_call_cents=tenant.plan.api_call_price_cents, input_microcents=tenant.plan.input_token_microcents, cached_microcents=tenant.plan.cached_input_microcents, output_microcents=tenant.plan.output_token_microcents)
    return event, cost

def refresh_usage_rollup(db: Session, tenant_id: int, now: datetime | None = None) -> UsageRollup:
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise ValueError("tenant not found")
    start, end = month_start(now), next_month_start(now)
    events = db.execute(select(UsageEvent).where(UsageEvent.tenant_id == tenant_id, UsageEvent.created_at >= start, UsageEvent.created_at < end)).scalars().all()
    api_used = sum(e.api_calls for e in events)
    token_used = sum(e.ai_tokens for e in events)
    cost = sum(estimate_cost_cents(e.api_calls, e.input_tokens, e.cached_input_tokens, e.output_tokens, e.reasoning_tokens, api_call_cents=tenant.plan.api_call_price_cents, input_microcents=tenant.plan.input_token_microcents, cached_microcents=tenant.plan.cached_input_microcents, output_microcents=tenant.plan.output_token_microcents) for e in events)
    month = start.strftime("%Y-%m")
    rollup = db.execute(select(UsageRollup).where(UsageRollup.tenant_id == tenant_id, UsageRollup.month == month)).scalar_one_or_none()
    if not rollup:
        rollup = UsageRollup(tenant_id=tenant_id, month=month)
        db.add(rollup)
    rollup.api_calls_used = api_used
    rollup.ai_tokens_used = token_used
    rollup.estimated_cost_cents = cost
    db.commit()
    db.refresh(rollup)
    return rollup
