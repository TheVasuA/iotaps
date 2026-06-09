"""Razorpay client abstraction (Task 15.1, Req 17).

The platform talks to Razorpay (the Payment_Gateway) for order creation and
verifies inbound webhooks by signature. To keep the codebase testable and to
guarantee that *no live API call and no real secret is ever required* in tests
or local dev, all Razorpay interaction goes through the small surface defined
here:

    - :class:`RazorpayClient` - creates orders. The default implementation does
      NOT hit the network: it mints a deterministic local order id. A real HTTP
      implementation can be swapped in for production without touching the
      billing service (dependency-injected via ``get_razorpay_client``).
    - :func:`verify_webhook_signature` - verifies the ``X-Razorpay-Signature``
      header using HMAC-SHA256 over the raw request body and the configured
      webhook secret (Req 17.2). This is the exact scheme Razorpay uses, so the
      same function validates real webhooks in production.

Amounts follow the Razorpay convention of the smallest currency unit (paise for
INR): ₹99 -> ``9900``. The pricing engine works in whole rupees, so the billing
service multiplies by 100 when creating an order and divides by 100 when
recording the rupee amount on a payment.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Razorpay expresses amounts in the smallest currency sub-unit (paise for INR).
PAISE_PER_RUPEE = 100


@dataclass(frozen=True)
class RazorpayOrder:
    """A created Razorpay order (the subset the platform persists/returns)."""

    id: str
    amount: int  # in paise
    currency: str
    receipt: Optional[str]
    status: str


@dataclass(frozen=True)
class RazorpayRefund:
    """A created Razorpay refund (the subset the platform persists/returns)."""

    id: str
    payment_id: str
    amount: int  # in paise
    currency: str
    status: str


class RazorpayClient:
    """Creates Razorpay orders.

    The default implementation is offline: it generates a local order id with
    the ``order_`` prefix Razorpay uses and echoes the request. This lets the
    subscribe flow be exercised end to end in tests and local development
    without credentials or network access. Production wiring can subclass this
    and override :meth:`create_order` to call the Razorpay Orders API.
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()

    def create_order(
        self,
        *,
        amount: int,
        currency: str = "INR",
        receipt: Optional[str] = None,
    ) -> RazorpayOrder:
        """Create an order for ``amount`` paise.

        Offline by default - returns a freshly minted order id without any
        external call (no real Razorpay secret required).
        """
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("Razorpay order amount must be a positive integer (paise)")
        order_id = f"order_{secrets.token_hex(10)}"
        logger.info(
            "razorpay_order_created",
            extra={"order_id": order_id, "amount": amount, "currency": currency},
        )
        return RazorpayOrder(
            id=order_id,
            amount=amount,
            currency=currency,
            receipt=receipt,
            status="created",
        )

    def create_refund(
        self,
        *,
        payment_id: str,
        amount: int,
        currency: str = "INR",
    ) -> RazorpayRefund:
        """Refund ``amount`` paise against a captured Razorpay payment.

        Offline by default - returns a freshly minted refund id without any
        external call (no real Razorpay secret required). Production wiring can
        override this to call the Razorpay Refunds API.
        """
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("Razorpay refund amount must be a positive integer (paise)")
        if not payment_id:
            raise ValueError("Razorpay refund requires a payment id")
        refund_id = f"rfnd_{secrets.token_hex(10)}"
        logger.info(
            "razorpay_refund_created",
            extra={
                "refund_id": refund_id,
                "payment_id": payment_id,
                "amount": amount,
                "currency": currency,
            },
        )
        return RazorpayRefund(
            id=refund_id,
            payment_id=payment_id,
            amount=amount,
            currency=currency,
            status="processed",
        )


def get_razorpay_client() -> RazorpayClient:
    """FastAPI dependency / factory returning the active Razorpay client."""
    return RazorpayClient()


@dataclass(frozen=True)
class RazorpayXPayout:
    """A submitted RazorpayX payout (the subset the platform persists)."""

    id: str
    amount: int  # in paise
    currency: str
    destination: Optional[str]
    status: str


class RazorpayXClient:
    """Transfers partner payouts via RazorpayX (Req 18.5).

    The default implementation is offline: it generates a local payout id with
    the ``pout_`` prefix RazorpayX uses and echoes the request, so the payout
    approval flow can be exercised in tests and local development without
    credentials or network access. Production wiring can subclass this and
    override :meth:`transfer` to call the RazorpayX Payouts API.
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()

    def transfer(
        self,
        *,
        amount: int,
        destination: Optional[str],
        currency: str = "INR",
    ) -> RazorpayXPayout:
        """Transfer ``amount`` paise to ``destination`` (bank/UPI).

        Offline by default - returns a freshly minted payout id without any
        external call (no real RazorpayX secret required).
        """
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("RazorpayX payout amount must be a positive integer (paise)")
        payout_id = f"pout_{secrets.token_hex(10)}"
        logger.info(
            "razorpayx_payout_transferred",
            extra={
                "payout_id": payout_id,
                "amount": amount,
                "currency": currency,
            },
        )
        return RazorpayXPayout(
            id=payout_id,
            amount=amount,
            currency=currency,
            destination=destination,
            status="processed",
        )


def get_razorpayx_client() -> RazorpayXClient:
    """FastAPI dependency / factory returning the active RazorpayX client."""
    return RazorpayXClient()


def expected_signature(payload_body: bytes, secret: str) -> str:
    """Compute the HMAC-SHA256 hex signature Razorpay sends for a webhook.

    Razorpay signs the *raw* request body with the webhook secret; the result
    is sent in the ``X-Razorpay-Signature`` header (Req 17.2).
    """
    return hmac.new(
        secret.encode("utf-8"), payload_body, hashlib.sha256
    ).hexdigest()


def verify_webhook_signature(
    payload_body: bytes, signature: Optional[str], secret: Optional[str]
) -> bool:
    """Whether ``signature`` is a valid Razorpay webhook signature for the body.

    Returns ``False`` (never raises) when the signature header is missing, the
    secret is unconfigured, or the HMAC does not match. Uses a constant-time
    comparison to avoid timing leaks. A missing secret fails closed so an
    unsigned/forgeable webhook is rejected rather than trusted (Req 17.2).
    """
    if not signature or not secret:
        return False
    computed = expected_signature(payload_body, secret)
    return hmac.compare_digest(computed, signature)
