import os
import stripe
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

PLATFORM_FEE_PERCENT = 20

# JPY is a zero-decimal currency in Stripe: unlike THB/USD, `amount` is the whole-yen
# value directly, not multiplied by 100. See DonationCheckoutCreate.amount.
CURRENCY = "jpy"

# Temporary stand-in for the real Account.create + Account Link onboarding flow.
# Maps farm_id -> the farm's connected account id.
FARM_STRIPE_ACCOUNTS = {
    1: "acct_1Ty4veKi17HfIpuy",
}


def get_farm_stripe_account_id(farm_id: int) -> str | None:
    return FARM_STRIPE_ACCOUNTS.get(farm_id)
