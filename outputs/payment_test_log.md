# Payment and delivery test log (MOCKED)

Everything below ran through the in-process MockPaymentProvider. No real or sandbox payment was made, no card details exist anywhere, and every order is test=true and excluded from every gate.

Run: `r20261117-025139-cb8b`

1. Simulated test purchase (MOCKED): order `ORD-1ad82131`, amount $39.00, test=true.
2. `payment.succeeded` event `evt_818b9fda09ed`: fee $1.43 (illustrative ASSUMPTION: 2.9% + $0.30, typical card-processor pricing), net $37.57, payout `po_2addcd09`.
3. Webhook handled: delivered=True; download token issued (24 h, HMAC-signed).
4. Webhook replay of the same event_id: status 200, duplicate=True, delivered=False. Deliveries for this order: 1.
5. Download before refund: 200 OK.
6. Refund attempted without founder approval: blocked (ApprovalRequired).
7. Refund approval requested: `AP-89711f64a4`, payload SHA-256 `76a6f65848ee04414085cce3cb09fc28807c1d477524259674f408155f6482eb`.
8. Founder approved the refund; refund executed: $39.00 (test=true).
9. Download after refund: 403 Forbidden (access revoked).
10. Reconciliation: 1 order(s), 0 mismatch(es), balanced=True. See phase5_step3_reconciliation.csv.
