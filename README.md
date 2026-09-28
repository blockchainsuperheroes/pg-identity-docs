# Pentagon Identity API — Developer Documentation

Public documentation for the Pentagon Identity API.

**Live docs:** [https://blockchainsuperheroes.github.io/pg-identity-docs/](https://blockchainsuperheroes.github.io/pg-identity-docs/)

## Contents

- **[PGAI wallet integration guide](pgai-wallet/README.md)** — the three account addresses
  (`penai_address` / `mm_address` / `aa_wallet_address`), PGAI bind + rotation, wallet login,
  and the encrypted cross-device sync relay

- **[White-label SSO integration guide](white-label-sso/README.md)** — passwordless email login for game titles: flows, response contract, new-brand request template, logo spec

- Authentication methods (email, wallet, magic link, SSO)
- Full endpoint reference
- App Key system & migration guide
- VIP Developer API access
- Code examples (JavaScript, Unity/C#, Python, cURL)

## API Base URL

```
https://api.account.pentagon.games
```

## Quick Start

1. Get an App Key from the Pentagon Games team
2. Add `X-PG-App-Key: pk_live_xxx` header to your API calls
3. Use `/user/login` to authenticate and get a JWT token
4. Use the JWT as `Authorization: Bearer <token>` for subsequent requests

## Signing users in — read this first

Every Pentagon front-end signs in through **the pill** (the PC Connector). Do not build your own
login form: that guidance is withdrawn, and it led several sites to collect real Pentagon passwords
on their own origins.

**Canonical standard:** [PENTAGON-LOGIN-STANDARD.md](https://github.com/blockchainsuperheroes/pentagon-login-widget-pill/blob/main/PENTAGON-LOGIN-STANDARD.md)

```html
<div data-pc-connector></div>
<script src="https://pentagon.games/connector/pc-connector.js" data-client-id="your-client-id"></script>
```

The pill shows balances as well as handling login, and that is the point: no wallet can show Points,
and MetaMask will not show $PC unless the user has added chain 3344 by hand.

This repo remains the **API reference** — endpoints, user resolution, wallet binding, NFT data, VIP.

## AA2 migration — read if you display a balance or an address

Every user’s Points are moving to a per-user **AA2 smart-contract account**. After a user migrates,
their old custodial address is swept to ~0.

> **Read `aa_wallet_address` and `npc_points` from `GET /user/walletinfo`** (nested under `result`).
> Never use `centralised_wallet_address`, never read `user_wallet` from Postgres, never derive an
> address, never hard-code one. All of those show **0 Points** after migration.

`mm_address` (the user’s own wallet) never changes. Spending is central: purchases go through
**payments.pentagon.games/stores**, which already pays from AA2, so most integrations need no new
payment path. Full detail, including the server-to-server lookups and the DNA rules:
[AA2 migration section](https://blockchainsuperheroes.github.io/pg-identity-docs/#aa2-migration).

## App Keys

Status (verified 2026-09-28): `X-PG-App-Key` is **logged but not enforced** on login/signup. The old
May 28, 2026 deadline passed without enforcement being enabled and no new date is set. Send it anyway —
some endpoints already require it. Use a **web** key in browser code; never ship a **server** key to a browser.

**A registered client id does not grant API CORS.** Sign-in registration and the API CORS allowlist are
separate lists. Call this API **server-side** unless your exact origin is confirmed on the CORS allowlist.
