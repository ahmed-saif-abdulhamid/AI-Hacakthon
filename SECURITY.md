# Security policy

## Supported versions

Security fixes go into the `main` branch and the next release. Older releases are not patched.

## Reporting a vulnerability

Please report a vulnerability privately through GitHub's **Report a vulnerability** button on the repository's Security tab, not in a public issue. Include the steps to reproduce it and what an attacker could do. We aim to reply within 7 days and to fix a confirmed issue within 30 days, and we credit reporters who want to be named.

## What counts

The guarantees ProveIt makes, and so the reports we most want:

- **Founder approval:** anything that publishes a page, opens a store or refunds without the founder approving the exact bytes (`@gated` in `proveit/approval.py`).
- **Money and data:** payments are MOCKED and no card numbers or passwords are stored; anything that stores them, or moves money, is a vulnerability.
- **Secrets:** a key, token or `SECRET_KEY` that leaks into logs, outputs, the decision log or an HTTP response.
- **Delivery:** a download that still works after a refund, or a webhook that delivers twice or accepts an unsigned event.
- **The HTTP layer:** bypasses of the same-origin, rate-limit or read-only demo protections in `app/security.py`.

Guard prompts that get past the input or output rules are welcome too; add them to `evals/trick_prompts.yaml` in a pull request when they are not sensitive.

## Out of scope

Rate limits or outages of the public sources (Hacker News, Stack Exchange, GitHub, Wikipedia), and findings that need a modified local install.
