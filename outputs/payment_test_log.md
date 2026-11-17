# Payment and delivery test log (MOCKED)

Everything below ran through the in-process MockPaymentProvider. No real or sandbox payment was made, no card details exist anywhere, and every order is test=true and excluded from every gate.

Run: `r20261117-105650-2561`

1. Simulated test purchase (MOCKED): order `ORD-12057d62`, amount $39.00, test=true.
2. `payment.succeeded` event `evt_19519d029e5e`: fee $1.43 (illustrative ASSUMPTION: 2.9% + $0.30, typical card-processor pricing), net $37.57, payout `po_a47a2559`.
3. Webhook handled: delivered=True; download token issued (24 h, HMAC-signed).
4. Webhook replay of the same event_id: status 200, duplicate=True, delivered=False. Deliveries for this order: 1.
5. Download before refund: 200 OK.
6. Refund attempted without founder approval: blocked (ApprovalRequired).
7. Refund approval requested: `AP-8426d44b4b`, payload SHA-256 `4a7758d78763dd765669d2439ae288a29ac7c3551c87d079b8d77b878ef5db2e`.
8. Founder approved the refund; refund executed: $39.00 (test=true).
9. Download after refund: 403 Forbidden (access revoked).
10. Reconciliation: 1 order(s), 0 mismatch(es), balanced=True. See phase5_step3_reconciliation.csv.
