# Pentagon Identity API — Developer Documentation

Public documentation for the Pentagon Identity API.

**Live docs:** [https://blockchainsuperheroes.github.io/pg-identity-docs/](https://blockchainsuperheroes.github.io/pg-identity-docs/)

## Contents

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

## Migration Deadline

**May 28, 2026** — All login/signup requests must include an `X-PG-App-Key` header.

See the [migration guide](https://blockchainsuperheroes.github.io/pg-identity-docs/#migration) for details.
