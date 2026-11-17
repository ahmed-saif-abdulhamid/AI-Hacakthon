"""Checkout (MOCKED): one test purchase from order to delivery.

Creates a test order, has the mock provider confirm payment with a signed ``payment.succeeded``
event, and hands that event to the webhook handler, which delivers the download. No real or
sandbox payment happens and no card details are asked for; every order is test=true.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import payments, webhooks


@dataclass
class Purchase:
    order_id: str
    event: dict  # the signed payment event, kept so callers can replay it
    result: dict  # the webhook handler's answer: delivered, duplicate, token


def purchase(run_id: str, amount: float) -> Purchase:
    provider = payments.MockPaymentProvider()
    order_id = provider.create_order(run_id, amount)
    event = provider.create_checkout(order_id, amount)
    return Purchase(order_id, event, webhooks.handle(event))
