from pydantic import BaseModel, Field

class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

class TenantOut(BaseModel):
    id: int
    name: str
    plan: str
    subscription_status: str

class GenerateRequest(BaseModel):
    tenant_id: int
    api_calls: int = Field(default=1, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)

class GenerateResponse(BaseModel):
    event_id: int
    api_calls_added: int
    ai_tokens_added: int
    estimated_cost_cents: int

class UsageResponse(BaseModel):
    tenant_id: int
    month: str
    api_calls_used: int
    api_calls_limit: int
    ai_tokens_used: int
    ai_tokens_limit: int
    estimated_cost_cents: int

class CheckoutRequest(BaseModel):
    tenant_id: int

class CheckoutResponse(BaseModel):
    session_id: str
    checkout_url: str
