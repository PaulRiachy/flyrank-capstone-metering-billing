import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from app.config import settings

@dataclass
class CheckoutSession:
    session_id: str
    checkout_url: str
    stripe_customer_id: str
    stripe_subscription_id: str

class MockStripeProvider:
    def create_checkout_session(self, tenant_id: int) -> CheckoutSession:
        suffix = uuid.uuid4().hex
        return CheckoutSession(f"cs_test_{suffix}", f"https://mock.stripe.local/checkout/cs_test_{suffix}", f"cus_test_{tenant_id}", f"sub_test_{suffix}")

    def sign_event(self, payload: bytes) -> str:
        return hmac.new(settings.webhook_secret.encode(), payload, hashlib.sha256).hexdigest()

    def build_event(self, event_id: str, event_type: str, tenant_id: int, plan_name: str = "pro", status: str = "active", subscription_id: str = "sub_test_1") -> bytes:
        body = {"id": event_id, "type": event_type, "data": {"tenant_id": tenant_id, "plan_name": plan_name, "status": status, "stripe_subscription_id": subscription_id, "stripe_customer_id": f"cus_test_{tenant_id}"}}
        return json.dumps(body, separators=(",", ":")).encode()

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        return hmac.compare_digest(self.sign_event(payload), signature)
