"""Dodo Payments — hosted checkout + signed webhooks (USDT payouts).

Merchant-of-record payments that settle to the business in USDT (works in
markets Stripe doesn't serve, e.g. Ethiopia). Flow:

1. Frontend POST /api/checkout {kind, pack|plan} -> ``create_checkout_session``
   builds a Dodo checkout (product_cart + metadata that ties it back to the
   TrimAura user), stores a ``payment`` row with status=pending, returns the
   hosted ``checkout_url``.
2. Customer pays on Dodo's hosted page; Dodo redirects them to return_url.
3. Dodo POSTs signed webhooks to /api/webhooks/dodo:
     - payment.succeeded      -> grant top-up credits (idempotent on event_id)
     - subscription.active    -> raise tier to starter/pro + set period_end
     - subscription.cancelled / .expired / .failed / .paused / .on_hold
                              -> drop the tier back to free
     - refund.succeeded       -> revoke the credits that were granted
   Events with invalid signatures are rejected; unknown event types are
   acknowledged and ignored (they cost nothing to apply).
"""

import logging
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.models import MonthlyUsage, Payment, UserTier

logger = logging.getLogger(__name__)

_client = None

# Map our internal plan/pack keys to Dodo product ids (from settings) and to
# the credits/price a top-up grants. Prices in USD.
_TOPUP_PACKS = {
    "250": {"product": "dodo_product_topup_250", "credits": "topup_pack_250_credits", "price": "topup_pack_250_price"},
    "500": {"product": "dodo_product_topup_500", "credits": "topup_pack_500_credits", "price": "topup_pack_500_price"},
}
_PLANS = {"starter": "dodo_product_starter", "pro": "dodo_product_pro"}


# --- Client ----------------------------------------------------------------

def dodo_client():
    """Lazily build the Dodo API client (test or live per settings)."""
    global _client
    if _client is None:
        if not settings.dodo_api_key:
            raise HTTPException(
                503,
                "Payments aren't wired up yet — try again soon.",
            )
        from dodopayments import DodoPayments

        _client = DodoPayments(
            bearer_token=settings.dodo_api_key,
            webhook_key=settings.dodo_webhook_key or None,
            environment="test_mode" if settings.dodo_test_mode else "live_mode",
        )
    return _client


# --- Checkout --------------------------------------------------------------

def create_checkout_session(user_id: str, kind: str, pack: str | None = None,
                            plan: str | None = None) -> dict:
    """Create a Dodo hosted checkout for a top-up pack or a subscription.

    Returns {"checkout_url", "session_id"} for the frontend to redirect to.
    """
    if kind == "topup":
        cfg = _TOPUP_PACKS.get(pack or "")
        if cfg is None:
            raise HTTPException(400, "Unknown top-up pack — pick '250' or '500'.")
        product_id = getattr(settings, cfg["product"], "")
        credits = int(getattr(settings, cfg["credits"], 0))
        amount_cents = int(round(getattr(settings, cfg["price"], 0) * 100))
        if not product_id or credits <= 0:
            raise HTTPException(503, "Top-up packs aren't configured yet.")
    elif kind == "subscription":
        attr = _PLANS.get(plan or "")
        if attr is None:
            raise HTTPException(400, "Unknown plan — pick 'starter' or 'pro'.")
        product_id = getattr(settings, attr, "")
        if not product_id:
            raise HTTPException(503, "Subscriptions aren't configured yet.")
        credits, amount_cents = 0, 0
    else:
        raise HTTPException(400, "kind must be 'topup' or 'subscription'.")

    checkout = dodo_client().checkout_sessions.create(
        product_cart=[{"product_id": product_id, "quantity": 1}],
        metadata={
            "user_id": user_id,
            "kind": kind,
            "pack": pack or "",
            "plan": plan or "",
            "credits": credits,
        },
        return_url=settings.checkout_return_url or None,
        cancel_url=settings.checkout_return_url or None,
    )

    with Session(engine) as session:
        session.add(Payment(
            session_id=checkout.session_id,
            user_id=user_id,
            kind=kind,
            plan=plan if kind == "subscription" else None,
            credits=credits,
            amount_cents=amount_cents,
            currency="USD",
        ))
        session.commit()

    return {"checkout_url": checkout.checkout_url, "session_id": checkout.session_id}


# --- Webhooks --------------------------------------------------------------

def verify_webhook(payload: str, headers: dict) -> object:
    """Verify the Dodo signature and return the typed event. 400 on bad sig."""
    if not settings.dodo_webhook_key:
        raise HTTPException(503, "Webhooks aren't configured yet.")
    try:
        return dodo_client().webhooks.unwrap(payload, headers=headers)
    except Exception as exc:  # noqa: BLE001 — any SDK error = bad/forged webhook
        logger.warning("Dodo webhook signature check failed: %s", exc)
        raise HTTPException(400, "Invalid webhook signature")


def handle_event(event) -> None:
    """Apply a verified webhook event. All handlers are idempotent."""
    etype = getattr(event, "type", "")
    data = getattr(event, "data", None)
    logger.info("Dodo webhook: %s", etype)
    if etype == "payment.succeeded":
        _on_payment_succeeded(data)
    elif etype == "subscription.active":
        _on_subscription_active(data)
    elif etype in ("subscription.cancelled", "subscription.expired",
                   "subscription.failed", "subscription.paused",
                   "subscription.on_hold"):
        _on_subscription_ended(data)
    elif etype == "refund.succeeded":
        _on_refund(data)
    else:
        logger.info("Ignoring Dodo webhook event type %r", etype)


def _on_payment_succeeded(payment) -> None:
    """Grant purchased credits / apply the subscription tier. Idempotent."""
    if payment is None:
        return
    metadata = payment.metadata or {}
    user_id = str(metadata.get("user_id") or "")
    kind = metadata.get("kind") or ""
    if not user_id:
        logger.warning("payment.succeeded without user_id in metadata; skipping")
        return

    with Session(engine) as session:
        row = session.exec(
            select(Payment).where(Payment.session_id == payment.checkout_session_id)
        ).first()
        if row is None:
            # Checkout row missing (e.g. created before this code shipped) —
            # reconstruct from metadata so paid credits are never dropped.
            row = Payment(
                session_id=payment.checkout_session_id,
                user_id=user_id,
                kind=kind,
                plan=metadata.get("plan") or None,
                credits=int(metadata.get("credits") or 0),
            )
            session.add(row)

        if row.status == "succeeded":
            return  # already applied — ack the retry silently

        row.payment_id = payment.payment_id
        row.amount_cents = payment.total_amount or 0
        row.currency = payment.currency or row.currency
        row.status = "succeeded"
        row.updated_at = datetime.now(UTC)

        if kind == "topup" and row.credits > 0:
            _grant_credits(session, user_id, row.credits)
        elif kind == "subscription":
            # Belt-and-braces: raise the tier now; subscription.active will
            # keep it refreshed on renewal. Plan comes from checkout metadata.
            plan = row.plan or metadata.get("plan") or ""
            _apply_tier(session, user_id, plan, subscription_id=payment.subscription_id)

        session.commit()


def _on_subscription_active(subscription) -> None:
    """Set the tier from the active subscription (idempotent, re-sent monthly)."""
    if subscription is None:
        return
    plan = _plan_for_product(subscription.product_id)
    if plan is None:
        logger.warning("subscription.active for unknown product %s", subscription.product_id)
        return
    user_id = _user_for_subscription(subscription, plan)
    if not user_id:
        return
    with Session(engine) as session:
        _apply_tier(
            session,
            user_id,
            plan,
            subscription_id=subscription.subscription_id,
            period_end=subscription.next_billing_date,
            status=subscription.status,
        )
        session.commit()


def _on_subscription_ended(subscription) -> None:
    """Downgrade to free when a subscription stops being active."""
    if subscription is None:
        return
    plan = _plan_for_product(subscription.product_id)
    user_id = _user_for_subscription(subscription, plan)
    if not user_id:
        return
    with Session(engine) as session:
        row = session.get(UserTier, user_id)
        if row is None:
            row = UserTier(user_id=user_id, tier="free")
            session.add(row)
        row.tier = "free"
        row.subscription_status = subscription.status
        row.updated_at = datetime.now(UTC)
        session.commit()


def _on_refund(refund) -> None:
    """Revoke credits that a refunded payment granted. Idempotent."""
    if refund is None:
        return
    with Session(engine) as session:
        row = session.exec(
            select(Payment).where(Payment.payment_id == refund.payment_id)
        ).first()
        if row is None or row.status != "succeeded":
            return
        if row.kind == "topup" and row.credits > 0:
            usage = session.get(MonthlyUsage, (row.user_id, datetime.now(UTC).strftime("%Y-%m")))
            if usage is not None and usage.topup_credits > 0:
                usage.topup_credits = max(0, usage.topup_credits - row.credits)
        row.status = "refunded"
        row.updated_at = datetime.now(UTC)
        session.commit()


# --- Helpers ---------------------------------------------------------------

def _grant_credits(session: Session, user_id: str, credits: int) -> None:
    """Add purchased credits on top of the tier's monthly allowance."""
    month = datetime.now(UTC).strftime("%Y-%m")
    usage = session.get(MonthlyUsage, (user_id, month))
    if usage is None:
        usage = MonthlyUsage(user_id=user_id, month=month)
        session.add(usage)
    usage.topup_credits += credits


def _apply_tier(session: Session, user_id: str, plan: str,
                subscription_id: str | None = None,
                period_end: datetime | None = None,
                status: str = "active") -> None:
    if plan not in settings.tier_limits:
        return
    row = session.get(UserTier, user_id)
    if row is None:
        row = UserTier(user_id=user_id, tier="free")
        session.add(row)
    row.tier = plan
    row.subscription_status = status
    row.subscription_id = subscription_id or row.subscription_id
    row.period_end = period_end
    row.updated_at = datetime.now(UTC)


def _plan_for_product(product_id: str) -> str | None:
    for plan, attr in _PLANS.items():
        if product_id and product_id == getattr(settings, attr, ""):
            return plan
    return None


def _user_for_subscription(subscription, plan: str | None) -> str:
    """Resolve the TrimAura user for a subscription webhook.

    Prefers the user_id we stamped in checkout metadata; falls back to the
    most recent payment row for the same plan (covers missing metadata).
    """
    meta = subscription.metadata or {}
    if meta.get("user_id"):
        return str(meta["user_id"])
    if plan is None:
        return ""
    with Session(engine) as session:
        row = session.exec(
            select(Payment).where(
                Payment.kind == "subscription",
                Payment.plan == plan,
            ).order_by(Payment.id.desc())
        ).first()
        return row.user_id if row else ""


def get_payment_status(session_id: str) -> dict | None:
    """Public status of one checkout (used by the frontend after redirect)."""
    with Session(engine) as session:
        row = session.exec(
            select(Payment).where(Payment.session_id == session_id)
        ).first()
        if row is None:
            return None
        return {
            "status": row.status,
            "kind": row.kind,
            "plan": row.plan,
            "credits": row.credits,
            "amount_cents": row.amount_cents,
            "currency": row.currency,
        }
