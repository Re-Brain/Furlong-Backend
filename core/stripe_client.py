import os
import stripe
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Points at the deployed frontend in production; falls back to the local dev
# server so nothing breaks for anyone who hasn't set this yet.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

PLATFORM_FEE_PERCENT = 20

# JPY is a zero-decimal currency in Stripe: unlike THB/USD, `amount` is the whole-yen
# value directly, not multiplied by 100. See DonationCheckoutCreate.amount.
CURRENCY = "jpy"
