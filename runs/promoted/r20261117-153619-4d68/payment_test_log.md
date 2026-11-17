# Payment and delivery test log (MOCKED)

Everything below ran through the in-process MockPaymentProvider. No real or sandbox payment was made, no card details exist anywhere, and every order is test=true and excluded from every gate.

Run: `r20261117-153619-4d68`

1. Simulated test purchase (MOCKED): order `ORD-63079769`, amount $39.00, test=true.
2. `payment.succeeded` event `evt_a75e89416ad4`: fee $1.43 (illustrative ASSUMPTION: 2.9% + $0.30, typical card-processor pricing), net $37.57, payout `po_37b28cff`.
3. Webhook handled: delivered=True; download token issued (24 h, HMAC-signed).
4. Webhook replay of the same event_id: status 200, duplicate=True, delivered=False. Deliveries for this order: 1.
5. Download before refund: 200 OK.
6. Refund attempted without founder approval: blocked (ApprovalRequired).
7. Refund approval requested: `AP-505c1eaf64`, payload SHA-256 `b2f002720de00cfea0438fc11ac5bb259e470fe5cf24dc95306f4d91f8975001`.
8. Founder approved the refund; refund executed: $39.00 (test=true).
9. Download after refund: 403 Forbidden (access revoked).
10. Reconciliation: 1 order(s), 0 mismatch(es), balanced=True. See the reconciliation file (Phase 5, step 3).
