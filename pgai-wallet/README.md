# PGAI wallet — addresses, binding, rotation & cross-device sync

Everything an integrator needs for the Pentagon AI (PGAI) wallet: which of the three addresses on
an account is which, how a PGAI address is bound and rotated, how it works as a login credential,
and how the encrypted cross-device sync relay behaves.

**Base URL:** `https://api.account.pentagon.games` — all paths below are relative to it.
All login/signup calls still require `X-PG-App-Key: pk_live_…` (see the
[main docs](https://blockchainsuperheroes.github.io/pg-identity-docs/#app-keys)).

---

## 0. Three addresses, three owners — read this first

This is the single most common integration mistake: treating all three as "the user's wallet".
They have **different custody models** and are not interchangeable.

| Field | User-facing name | Custody | Rotatable? | Chain |
|---|---|---|---|---|
| `penai_address` | Pentagon AI wallet (PGAI) | **Self-custodial** — the key is generated and held on the user's device. Pentagon never sees it. | **Yes** (capped, section 3) | Pentagon Chain (3344) |
| `mm_address` | Connected wallet | **User's own external wallet** (MetaMask, Rabby, Phantom, WalletConnect…). Watch-only from our apps' point of view — we read it, we never sign with it. | No — one-time, irreversible bind | Whatever the user's wallet is on |
| `aa_wallet_address` | **"PG Balance"** | **Custodial** — created automatically at email signup. Pentagon holds the key server-side and signs on the user's behalf. | n/a | Pentagon Chain (3344) |

### `aa_wallet_address` is NOT account abstraction

Despite the `aa_` prefix, this is a **plain custodial EOA**. It is created with a standard
`eth_account` keypair at signup, and the encrypted private key is stored by the identity backend.
There is no ERC-4337 bundler, no EntryPoint, no UserOperation, no smart-contract wallet anywhere
in this path.

The name is retained purely for **wire compatibility** — `aa_wallet_address` is the join key the
EtherFantasy DNA service and other downstream consumers already index on, and renaming it would
break them. Do not infer 4337 semantics from the field name.

`GET /user/walletinfo` returns it under **both** `wallet_address` and `aa_wallet_address`; they
are the same value.

### Which one do I use?

- **"Who is this user?"** → the PG account id from `GET /user/info`. Not an address.
- **"Where do I send in-app rewards / what does the user spend from?"** → `aa_wallet_address`
  (PG Balance), via the identity endpoints. Never derive it from a seed, never fetch it from
  mining.
- **"What did the user connect from their own wallet?"** → `mm_address`. Read-only.
- **"What is the user's on-device Pentagon AI wallet?"** → `penai_address`.

---

## 1. Where the addresses appear

| Call | Field | Notes |
|---|---|---|
| `GET /user/info` | `penai_address` | **New.** Empty/`null` until the user binds one. |
| `GET /user/info` | `mm_address` | Bound external wallet, or `null`. |
| `GET /user/walletinfo` | `aa_wallet_address`, `wallet_address` | Same value; plus `pc_balance`, `npc_points`, `live_balance`. |
| `GET /user/penai/history` | `current` | The currently bound PGAI address (section 3). |

---

## 2. `POST /user/penai/bind` — bind or rotate the PGAI address

**Auth:** `Authorization: Bearer <JWT>`. The address is bound to the calling user; there is no
way to bind on someone else's behalf.

```http
POST /user/penai/bind
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "address":    "0xabc…",
  "signature":  "0x…",
  "message":    "Sign up to Pentagon Games,1753400000",
  "login_from": "pentagon-ai-extension"
}
```

| Field | Required | Notes |
|---|---|---|
| `address` | yes | Lowercased server-side before storage and comparison. |
| `signature` | yes | `personal_sign` (EIP-191) over `message`, produced by the key for `address`. |
| `message` | yes | Exactly `Sign up to Pentagon Games,<unixSeconds>` — see below. |
| `login_from` | no | Recorded in the address history (section 4). |

### The signed message

Same `personal_sign` scheme as `/user/bind_metamask`: the backend recovers the signer from
`message` + `signature` and requires it to equal `address`.

```
Sign up to Pentagon Games,<unixSeconds>
```

**Freshness:** the shared signature checker reads the value after the **last comma** as a Unix
timestamp and rejects the signature once it is **more than 5 minutes old**. Sign at the moment of
binding; do not cache a signed message. (The bind view additionally logs a warning on skew beyond
a day — that one is diagnostic only and does not fail the request.)

### Success

```json
{
  "status": true,
  "result": { "penai_address": "0xabc…" }
}
```

### Rotation vs. the MetaMask bind

| | `bind_metamask` (`mm_address`) | `penai/bind` (`penai_address`) |
|---|---|---|
| Re-bind a different address | **Rejected** — "You already have MetaMask wallet connected". One-time and irreversible. | **Allowed**, within the caps in section 3. The new address replaces the old one. |
| Old value after a change | n/a | Retained in the address history with `released_at` stamped. Never silently lost. |

### Uniqueness

A PGAI address may belong to **exactly one** PG account. If the address is already bound to a
different account the bind is refused:

```json
{ "status": false, "message": "This wallet is already linked to another Pentagon account." }
```

This is enforced by a unique DB constraint as well as an up-front check, so a race between two
simultaneous binds still fails safely rather than moving the address.

### Re-binding the address you already have is a free no-op

If `address` equals the account's current `penai_address`, the call returns success, writes no new
history row, and **does not consume a rotation**. Clients may call bind idempotently on every
unlock without burning the user's quota.

### Errors

| `message` | Cause |
|---|---|
| `Invalid Signature` | Signature does not recover to `address`, or the timestamp is older than 5 minutes. |
| `This wallet is already linked to another Pentagon account.` | Address bound to a different PG account. |
| `You have changed your Pentagon AI address too many times. Contact support.` | A rotation cap was hit (section 3). |
| `Validation error` | Missing `address` / `signature` / `message`; details in `erorlist`. |

> **Convention:** application-level failures come back as **HTTP 200** with `"status": false`.
> Branch on `status`, not on the HTTP code. Only missing/invalid JWTs produce `401`
> (`{"detail": "Authentication credentials were not provided."}` /
> `{"detail": "Token is invalid"}`).

---

## 3. Rotation limits

`penai_address` is a single column that is overwritten on rotation, so every bind is mirrored into
an append-only history table and capped:

| Cap | Value | Counts |
|---|---|---|
| Lifetime | **5 distinct addresses** | Every distinct address the account has ever held. |
| Rolling window | **3 binds per 30 days** | History rows created in the last 30 days (sliding, not calendar). |

Both caps are checked **before** anything is written — a refused rotation leaves the current
address untouched. Re-binding the current address is exempt from both.

Users who bound a PGAI address before the history feature shipped have no history rows; the first
rotation backfills a row for the address they are about to lose, so the trail is complete either
way.

---

## 4. `GET /user/penai/history` — the address trail

**Auth:** `Authorization: Bearer <JWT>`. Returns the calling user's own rows only.

```json
{
  "status": true,
  "result": {
    "current": "0xnew…",
    "addresses": [
      {
        "address":     "0xnew…",
        "bound_at":    "2026-08-01T09:12:44.318Z",
        "released_at": null,
        "login_from":  "pentagon-ai-telegram"
      },
      {
        "address":     "0xold…",
        "bound_at":    "2026-06-14T20:03:01.552Z",
        "released_at": "2026-08-01T09:12:44.318Z",
        "login_from":  "pentagon-ai-extension"
      }
    ],
    "rotations_used": 2,
    "rotations_remaining": 3
  }
}
```

| Field | Meaning |
|---|---|
| `current` | The address currently bound. `""` when the user has never bound one. |
| `addresses` | Newest first. `released_at: null` marks the row for `current`; every other row carries the moment it was replaced. |
| `login_from` | Which app performed that bind — `""` when the client did not send one. |
| `rotations_used` | Count of **distinct** addresses ever held (matches the lifetime cap). |
| `rotations_remaining` | `5 - rotations_used`, floored at 0. |

Typical UI use: "Your Pentagon AI account was set up in **Pentagon AI on Telegram**" — read
`login_from` off the entry for `current`. Treat an empty or unrecognised value as unknown and hide
the line; never block on it.

---

## 5. Wallet login now accepts the PGAI address

`POST /user/login` with `type: "wallet"` matches the signed address against **either**
`mm_address` **or** `penai_address`. A device-held PGAI key is therefore a full login credential —
this is what powers silent re-login after unlock in the Pentagon AI clients.

```http
POST /user/login
Content-Type: application/json
X-PG-App-Key: pk_live_your_key

{
  "type":       "wallet",
  "address":    "0xabc…",
  "signature":  "0x…",
  "message":    "Sign up to Pentagon Games,1753400000",
  "login_from": "pentagon-ai-extension"
}
```

The backend does not require a particular message *prefix* — it requires that the signature
recovers to `address` and that the timestamp after the last comma is under 5 minutes old. The
Pentagon AI clients reuse the bind message verbatim.

**`type` accepts only `"email"` and `"wallet"`.** There is no `"username"`, `"pns"` or `"penai"`
type — `"email"` runs the canonical
[resolution chain](https://blockchainsuperheroes.github.io/pg-identity-docs/#user-resolution)
(email → PNS → username → legacy) and any other value is rejected with
`{"status": false, "message": "Validation error", "erorlist": {"type": ["This field is required."]}}`.

Success is the standard shape, unchanged:

```json
{
  "status": true,
  "result": {
    "access_token":  "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
  }
}
```

---

## 6. `login_from` — which app is the user in?

`login_from` is an optional free-text client identifier sent on `POST /user/login`,
`POST /user/bind_metamask` and `POST /user/penai/bind`. On `penai/bind` it is persisted into the
address history, which is what lets a freshly installed client tell the user *where* their account
was originally set up.

Known values used by the first-party Pentagon AI clients:

| Value | Client |
|---|---|
| `pentagon-ai-telegram` | Pentagon AI on Telegram |
| `pentagon-ai-extension` | Pentagon AI browser extension |
| `pentagon-ai-mobile` | Pentagon AI mobile app |
| `pentagon-ai` | Generic fallback when a host app sets nothing |

It is **client-supplied and unvalidated** — treat it as a display hint, never as an authorisation
signal. Third-party integrators should send their own app name.

---

## 7. Cross-device wallet sync — the server is a dumb relay

Moving a self-custodial PGAI wallet from a device that has it (**source**) to a device that wants
it (**target**), without the seed ever reaching Pentagon.

### Security model — state it plainly to your users

- The server stores **only** an ephemeral **public** key and an **opaque ciphertext blob**. It
  holds no private key and **cannot decrypt** the payload.
- **Both devices must be authenticated as the same PG account.** Every view scopes its queryset to
  `request.user`; a channel id belonging to another account resolves to "Channel not found".
- **10-minute TTL.** Channels older than that are dead and their ciphertext is blanked.
- **Single read.** `sync/fetch` hands the blob over exactly once, then wipes it and flips the
  channel to `delivered`. A replayed channel id gets nothing.
- **Server-generated channel ids.** The caller cannot choose or guess one.
- **Supersede.** Opening a channel expires the user's other pending channels, so the source device
  only ever sees the latest request.

The ciphertext is opaque to the backend — the encryption scheme is entirely a client concern. The
reference Pentagon AI clients seal with ephemeral **X25519** key agreement → **HKDF-SHA256**
(bound to both public keys) → **XChaCha20-Poly1305**, and display a 4-digit safety code derived
from the public keys so the user can number-match the two devices before approving.

### Flow

```mermaid
sequenceDiagram
    participant T as Target device
    participant API as api.account.pentagon.games
    participant S as Source device
    T->>API: POST user/sync/open {target_pubkey, target_label, safety_code}
    API-->>T: {channel_id, expires_in: 600}
    S->>API: GET user/sync/pending
    API-->>S: [{channel_id, target_pubkey, target_label, safety_code, created_at}]
    Note over T,S: User compares the safety code on both screens
    S->>API: POST user/sync/approve {channel_id, ciphertext}
    T->>API: POST user/sync/fetch {channel_id}
    API-->>T: {state: "approved", ciphertext}
    Note over API: blob wiped, channel -> delivered
```

### Endpoints

All five require `Authorization: Bearer <JWT>` and act only on the calling user's channels.

#### `POST /user/sync/open` — target opens a channel

```json
{ "target_pubkey": "<base64 ephemeral public key>", "target_label": "Chrome on Windows", "safety_code": "0042" }
```

`target_pubkey` is required (≤200 chars). `target_label` (≤120) and `safety_code` (≤12) are
optional and exist only so the source device can render a useful prompt.

```json
{ "status": true, "result": { "channel_id": "…", "expires_in": 600 } }
```

#### `GET /user/sync/pending` — source lists incoming requests

Returns only non-expired `pending` channels. **No ciphertext is ever returned here** — just the
metadata the approval prompt needs.

```json
{
  "status": true,
  "result": [
    {
      "channel_id":    "…",
      "target_pubkey": "<base64>",
      "target_label":  "Chrome on Windows",
      "safety_code":   "0042",
      "created_at":    "2026-08-05T11:20:03.114Z"
    }
  ]
}
```

#### `POST /user/sync/approve` — source posts the sealed blob

```json
{ "channel_id": "…", "ciphertext": "<opaque base64>" }
```

→ `{ "status": true }`. Only a `pending`, non-expired channel owned by the caller may be approved.
Failures: `Channel not found`, `Channel expired`, `Channel is <status>`.

#### `POST /user/sync/reject` — source declines

```json
{ "channel_id": "…" }
```

→ `{ "status": true }`. **Terminal.** The ciphertext field is cleared, the channel can never be
approved afterwards, and the target's next fetch gets a hard failure.

#### `POST /user/sync/fetch` — target polls, then reads once

```json
{ "channel_id": "…" }
```

| Channel state | Response |
|---|---|
| Waiting for the source | `{"status": true, "result": {"state": "pending"}}` |
| Approved (first fetch) | `{"status": true, "result": {"state": "approved", "ciphertext": "<base64>"}}` |
| Approved (any later fetch) | `{"status": false, "message": "Already delivered"}` |
| Rejected on the other device | `{"status": false, "message": "Request was rejected on the other device"}` |
| Expired / unknown to this user | `{"status": false, "message": "Channel expired"}` / `Channel not found` |

### Channel states

`pending` → `approved` → `delivered`, with `rejected` and `expired` as terminal side-exits.

### Client checklist

1. Never send a seed, mnemonic or private key to any Pentagon endpoint. The relay carries
   ciphertext only.
2. Keep the target's ephemeral secret key **in memory** for the life of the attempt; never persist
   or log it.
3. Show the safety code on **both** devices and require the human to match it before the source
   approves — that is what defeats a substituted key.
4. Poll `sync/fetch`, do not assume; handle `pending` for up to the 10-minute TTL and then give up
   cleanly.
5. Treat a failed decrypt as hostile, not as a retry: the blob is already consumed.

---

## 8. Downstream: the EtherFantasy DNA link

On a successful `penai/bind` the identity backend fires a best-effort, HMAC-SHA256-signed webhook
to the EF DNA service carrying `pgAccountId`, `aaWallet` and `pgaiAddress` — this is the join that
makes `aa_wallet_address` naming load-bearing (section 0). The webhook never blocks or fails the
bind; integrators do not call it and do not need to handle it.

---

## 9. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `Invalid Signature` on bind or wallet login | Message timestamp older than 5 minutes, or the message string does not byte-match what was signed. Re-sign at call time. |
| Bind succeeds but `rotations_remaining` did not drop | You re-bound the address already current — that is a deliberate free no-op. |
| `This wallet is already linked to another Pentagon account.` | The address is bound elsewhere. Addresses are single-account by design; generate a fresh wallet. |
| Wallet login returns `Unauthenticated user` | Neither `mm_address` nor `penai_address` on any account matches the signed address — bind first. |
| `sync/pending` is empty on the source device | The target's channel expired (10 min), or was superseded by a newer `sync/open`, or the two devices are logged into different PG accounts. |
| `sync/fetch` returns `Already delivered` | Single-read semantics: the blob was already handed out. Open a new channel. |
| Any call returns `401 {"detail": "Token is invalid"}` | Expired or malformed JWT — refresh via `POST /user/token/refresh`. |

---

*Maintained by the Pentagon identity session. Endpoints verified against production
(`api.account.pentagon.games`) on 2026-08-06. Last major update: 2026-08-06 (PGAI wallet concept,
`penai/bind` + `penai/history`, cross-device sync relay, wallet login via `penai_address`).*
