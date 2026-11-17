# Payment and delivery test log (MOCKED)

Everything below ran through the in-process MockPaymentProvider. No real or sandbox payment was made, no card details exist anywhere, and every order is test=true and excluded from every gate.

Run: `r20261117-201356-8496`

1. Simulated test purchase (MOCKED): order `ORD-5235b476`, amount $39.00, test=true.
2. `payment.succeeded` event `evt_709a08d10273`: fee $1.43 (illustrative ASSUMPTION: 2.9% + $0.30, typical card-processor pricing), net $37.57, payout `po_b5f66581`.
3. Webhook handled: delivered=True; download token issued (24 h, HMAC-signed).
4. Webhook replay of the same event_id: status 200, duplicate=True, delivered=False. Deliveries for this order: 1.
5. Download before refund: 200 OK.
6. Refund attempted without founder approval: blocked (ApprovalRequired).
7. Refund approval requested: `AP-7023bffa7b`, payload SHA-256 `15781c09b92146797d787762a4c915e22da5ecb37790c353432dd54ed81cb17d`.
8. Founder approved the refund; refund executed: $39.00 (test=true).
9. Download after refund: 403 Forbidden (access revoked).
10. Reconciliation: 1 order(s), 0 mismatch(es), balanced=True. See the reconciliation file (Phase 5, step 3).
