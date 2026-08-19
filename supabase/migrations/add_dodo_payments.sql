-- Dodo Payments (merchant-of-record; USDT payouts) checkout + subscription state.
-- Rows are created when a checkout session is issued, updated on webhooks.
-- session_id is UNIQUE so retried webhook deliveries can't double-grant credits.

CREATE TABLE IF NOT EXISTS payment (
    id SERIAL PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,           -- Dodo checkout_session_id (idempotency)
    payment_id TEXT,                           -- Dodo payment id (set on payment.succeeded; refunds match on it)
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'topup',        -- topup | subscription
    plan TEXT,                                 -- starter | pro for subscriptions
    credits INT NOT NULL DEFAULT 0,            -- credits granted for top-ups
    amount_cents INT NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL DEFAULT 'pending',    -- pending | succeeded | refunded | failed
    event_id TEXT,                             -- Dodo event id (dedupe)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payment_user_id ON payment (user_id);
CREATE INDEX IF NOT EXISTS idx_payment_status ON payment (status);

-- Recurring subscription state lives on the tier row (auto-apply on webhook).
ALTER TABLE user_tiers ADD COLUMN IF NOT EXISTS subscription_id TEXT;
ALTER TABLE user_tiers ADD COLUMN IF NOT EXISTS subscription_status TEXT;
ALTER TABLE user_tiers ADD COLUMN IF NOT EXISTS period_end TIMESTAMPTZ;
