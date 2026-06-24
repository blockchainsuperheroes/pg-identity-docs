# SPEC — Protected Email Relay (NPC-paid user-to-user mail)

> Status: DRAFT for review | Author: Cerise01 | 2026-06-24
> Builds on: Gmail SMTP Relay (`gmail_email.py`), `friend_email_v6.py`, NPC spend (`/user/npc/spend`), Tier-3 owner identity (card chat `IDENTITY_AWARE`).

---

## 1. What we're building (plain version)

Let one Pentagon user send a message to another Pentagon user **without either side knowing the
other's real email address**, paid for in NPC to keep it spam-resistant. Pentagon is the trusted
middleman that holds the real addresses and relays.

This is the "protected contact" pattern used by Chinese delivery/travel platforms (Meituan, Didi,
Ctrip): a rider and driver, or a guest and host, communicate through a platform-issued proxy
number/address; neither sees the other's real one, and the platform can rate-limit, log, and cut
off abuse. We do the email version of that.

Two surfaces use it:
1. **Protected address format** — `<username>+identity@pentagon.games` is a stable public alias.
   Anyone (or any system) can mail that alias; we look up the real user, gate it, and forward to
   their real inbox with the sender masked. The recipient's real address is never exposed.
2. **Card / app "Send a message" action** — a logged-in user, from someone's Pentagon card or
   profile, pays NPC and sends them a short message. We deliver it as a Pentagon system email.
   Neither party learns the other's raw email.

Payment (NPC) is the spam control: every relayed message costs the sender NPC, so blasting is
expensive, and the spend is already balance-gated + logged on-chain via the existing primitive.

---

## 2. Why NPC payment = spam control (design rationale)

- A free "email any user" button is a spam cannon. Requiring NPC per send makes bulk abuse cost
  real value, and we already have the rails: `/user/npc/spend` balance-gates, signs a PC tx, logs
  to `v2_npc_payments`, and splits/distributes. We reuse it verbatim with a new `action`.
- Pricing is a lever, not a fixed number. Suggested defaults in §7; tunable per relationship tier
  (cheaper/free to existing friends, more expensive to strangers).
- Payment also gives us a clean abuse-appeal trail: every relayed mail maps 1:1 to a paid,
  idempotent spend row with sender id, recipient id, timestamp, and tx hash.

---

## 3. The protected address format

```
<username>+identity@pentagon.games
```

- `nftprof+identity@pentagon.games` → resolves to user `nftprof` → relayed to their real inbox.
- The `+identity` tag namespaces this as the relay channel (vs. transactional `identity@`), and
  lets us add sibling tags later (`+billing`, `+support`) without new mailboxes.
- **Plus-addressing caveat:** Google Workspace delivers `identity+anything@` to the `identity@`
  mailbox, so inbound to any `...+identity@` style alias must be **caught and parsed**, not relied
  on as a native per-user mailbox. We therefore run an **inbound parser** (§5.2), not 1 mailbox
  per user. The format users SEE and SHARE is `<username>+identity@pentagon.games`; under the hood
  it all lands in / is processed against `identity@pentagon.games`.
- Alternative (cleaner, recommended long-term): a dedicated relay subdomain
  `<username>@msg.pentagon.games` with a catch-all → parser. Avoids plus-address ambiguity and
  reads better on a card. Phase 2; Phase 1 ships the `+identity` form since the mailbox exists.

---

## 4. The two flows

### 4.1 Outbound (the main one): user → user via card/app, NPC-paid

```
Sender (logged in, Tier 3 verified) on Recipient's card/profile
  → taps "Send a message" → writes short text
  → FE: NPC spend(action="protected_email", amount, idempotency_key)   [existing primitive]
        gated: balance check + PC tx + v2_npc_payments row  → tx_hash
  → FE: POST /user/relay/email/send  { recipient_handle, body, subject?, spend_tx / idem_key, viewerJwt }
  → Backend (ApiKeyAuth s2s OR user JWT):
        1. verify sender via JWT  (real sender id)            [reuse AgentSessionVerify path]
        2. resolve recipient by handle → real email           [User table]
        3. VERIFY the NPC spend really happened for THIS sender+action+idem  (anti-replay)
        4. relationship + rate-limit + block checks (§6)
        5. render Pentagon "you have a message" email (masked sender)
        6. SMTP relay send to recipient.email                 [reuse gmail_email send]
        7. log relay_message row (sender_id, recipient_id, spend_id, message_hash, ts)
  → recipient gets: "{SenderDisplayName} sent you a message via Pentagon" + body + Reply CTA
        Reply CTA → opens the relay thread on Pentagon (id.peg.gg), NOT a raw mailto.
```

Neither raw email is ever in the message. Sender sees only the recipient's handle; recipient sees
only the sender's display name + a Pentagon reply link.

### 4.2 Inbound (protected alias): someone mails `user+identity@pentagon.games`

```
External/User mails  nftprof+identity@pentagon.games
  → lands in identity@pentagon.games mailbox (Workspace plus-addressing)
  → inbound parser (poll via gog/IMAP, or Workspace push) reads it
  → parse intended recipient handle from the To/+tag
  → resolve recipient real email
  → spam/auth gates (§6): is the SENDER a known PG user? if yes, optionally NPC-gate or allow;
      if anonymous external, apply stricter spam rules / require it to be a reply to an existing
      relay thread, else drop or hold.
  → re-relay to recipient.email with sender masked, Reply-To set to a relay token address
  → log + thread it
```

Phase 1 can ship **outbound only** (4.1), which is the spam-controlled, paid, card-driven flow
Idon described. Inbound alias (4.2) is valuable but adds an inbound-mail parser; recommend Phase 2.

---

## 5. Backend components

### 5.1 New endpoints (on pentagon-login-backend, `:8031`, `api.account.pentagon.games`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/user/relay/email/send` | User JWT + verified NPC spend | Outbound paid relay (4.1) |
| GET  | `/user/relay/threads` | User JWT | List a user's relay threads (sent/received) |
| GET  | `/user/relay/thread/<id>` | User JWT (participant only) | Read a thread |
| POST | `/user/relay/email/reply` | User JWT (participant) | Reply within an existing thread (cheaper/free) |
| POST | `/user/relay/block` | User JWT | Block a sender from relaying to you |
| GET  | `/user/relay/quote` | User JWT | Get the NPC price to mail a given handle (tiered) |

All mirror the existing internal-view conventions (`ApiKeyAuth` for s2s where the card-chat proxy
calls them; user-JWT for direct FE calls). Reuse `_resolve_user`, `_display_name`, `UserFriendship`.

### 5.2 Inbound parser (Phase 2)

- Reuse `gog gmail search`/IMAP on `identity@pentagon.games` to poll unread, OR a Workspace
  Pub/Sub push. Parse `To:` for the `+identity` tag + username; resolve; gate; re-relay.
- Runs as a small supervisor service (`pentagon-relay-inbound`) next to the login backend, or a
  cron poll. Must dedupe on Message-ID and never loop (drop mail already from `identity@`).

### 5.3 Data model (new tables)

```sql
-- one row per relayed message
CREATE TABLE relay_message (
  id              BIGSERIAL PRIMARY KEY,
  thread_id       BIGINT NOT NULL REFERENCES relay_thread(id),
  sender_id       BIGINT NOT NULL REFERENCES auth_user(id),
  recipient_id    BIGINT NOT NULL REFERENCES auth_user(id),
  direction       SMALLINT NOT NULL,         -- 1=outbound(card), 2=inbound(alias)
  body            TEXT NOT NULL,
  subject         TEXT,
  spend_id        BIGINT REFERENCES v2_npc_payments(id),  -- the paying spend (null for free replies)
  message_hash    CHAR(64) NOT NULL,         -- sha256(sender|recipient|body|ts) for audit/dedupe
  smtp_status     TEXT,                      -- sent / failed / held
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE relay_thread (
  id              BIGSERIAL PRIMARY KEY,
  user_a          BIGINT NOT NULL,           -- canonical lower id
  user_b          BIGINT NOT NULL,           -- canonical higher id
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_a, user_b)
);

CREATE TABLE relay_block (
  blocker_id      BIGINT NOT NULL,
  blocked_id      BIGINT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (blocker_id, blocked_id)
);
```

Threading is symmetric (canonical user_a < user_b) so a back-and-forth stays one thread regardless
of who started it.

---

## 6. Anti-spam / safety gates (the heart of it)

Applied in order on every relay send; first failure stops it (sender already paid → refund/credit
NPC on a HARD reject, see §6.x):

1. **Sender verified.** Must be a real, verified PG user (JWT). Anonymous web cannot pay-relay in
   Phase 1.
2. **Recipient exists + has email + is verified.** Else reject (no charge / refund).
3. **NPC spend verified.** The referenced spend row must exist, belong to THIS sender, be for
   `action=protected_email`, unconsumed (idempotency_key not already tied to a relay_message), and
   recent. Prevents replay / paying once and sending many.
4. **Block list.** If recipient has blocked sender → silently accept-and-drop (looks sent to
   sender to avoid block-probing) OR reject; product call. Recommend silent-drop, no refund (you
   spent trying to mail someone who blocked you; cheap deterrent).
5. **Rate limits.** Per-sender global cap (e.g. N relays/hour), per-pair cap (e.g. can't mail the
   same recipient more than X/day), and a new-thread cap (opening threads with strangers is the
   spammy pattern → tighter). Counters off `relay_message`.
6. **Content limits.** Max body length (e.g. 2000 chars), strip/escape HTML, no attachments in
   Phase 1, URL count cap (spam links). Optionally run text through a lightweight spam classifier.
7. **Recipient preference.** Honor a per-user "who can relay to me" setting: everyone / friends
   only / nobody. Default: everyone-but-rate-limited (so the feature works out of the box) — Idon
   to confirm; friends-only is the safest default.

**Refund policy:** soft/gate failures the sender couldn't predict (recipient has no email, transient
SMTP fail) → refund/credit NPC. Failures that are the sender's fault (blocked, rate-limited, bad
content) → no refund. Refund = reverse/credit via the NPC ledger, not a new on-chain mint.

---

## 7. NPC pricing (tiered, tunable)

Reuses `npcOf(action)` / `amount_npc`. Suggested starting points (Idon to set):

| Scenario | Price | Why |
|----------|-------|-----|
| Reply within an existing thread | **free or tiny** | Already a consented conversation; don't tax replies. |
| Mail an existing **friend** | **low** | Low spam risk, encourage use. |
| Open a **new thread with a stranger** | **higher** | This is the spam vector; price it up. |
| Bulk / rapid (after N in an hour) | **escalating** | Soft cap via rising price. |

Price is fetched by FE via `/user/relay/quote?to=<handle>` so the button can show "Send for X NPC"
before the user commits.

---

## 8. Frontend (card + app)

- On a card/profile of user X (when viewer is logged in), show a **"Send a message" / envelope**
  action near the existing treat/NPC actions.
- Tapping opens a small composer: recipient shown as `@X` (no email), a text box, and a live
  "Send for {quote} NPC" button.
- On send: call `window.__npc.spend('protected_email', {recipient:X}, quoteNpc)`; on `ok`, POST
  `/user/relay/email/send` with the tx/idem + body + viewerJwt. Show "Sent ✓ — X will get it as a
  Pentagon message and can reply to you here."
- A **"Messages"** view lists relay threads (`/user/relay/threads`) so replies stay on-platform and
  we never expose addresses.
- The card chat agent (Irene) can ALSO offer this as a Tier-3 owner action later ("send a message
  to @alice for 5 NPC?") — but that routes through the SAME gated endpoint; the chat never sends
  mail itself (keeps the answer-only sandbox intact; the relay endpoint is the only mail path).

---

## 9. Email rendering (recipient's inbox)

Reuse the Gmail SMTP relay + the V6 visual system (header/footer standards in README). Key rules:

- **From:** `Pentagon Identity <identity@pentagon.games>` (never the sender's real address).
- **Sender shown as:** display name + `@handle` only, in the body, e.g. "**Alice (@alice)** sent
  you a message via Pentagon."
- **Reply-To:** a relay token address that routes back through us (Phase 2 inbound) OR, Phase 1,
  a Pentagon reply link (`https://id.peg.gg/messages/<thread>`), NOT a `mailto:` to the sender.
- Body = the user's text, escaped, in the standard dark card. Hosted PNG logo, JWT unsubscribe,
  standard footer — all per the existing README rules (no base64, no SVG).
- New `email_type = "relay_message"` in `pentagon_email_config` + a `_body_relay_message` builder
  registered in `BUILDERS`, following the README "How to Request a New Email Type" steps exactly.

---

## 10. Privacy & abuse posture

- Real emails live only in the User table + SMTP envelope; never in any rendered message, API
  response, or the card.
- Every relay is paid, logged, hashed, and attributable. Cut-off = block row; pattern abuse =
  rate-limit + price escalation + (optional) manual review queue for held messages.
- One-click unsubscribe / "stop receiving relayed messages" via the existing JWT unsubscribe +
  the per-user preference (§6.7). CAN-SPAM/GDPR aligned (we already do this for campaigns).
- Loop protection on inbound: drop anything already From `identity@`, dedupe on Message-ID.

---

## 11. Phasing

- **Phase 1 (ship first):** Outbound paid relay (4.1) — endpoints `/relay/email/send`, `/quote`,
  `/threads`, `/block`; new tables; `relay_message` email type; card "Send a message" action; all
  §6 gates; reuse NPC spend + Gmail relay. This is the complete spam-controlled user→user mail Idon
  asked for.
- **Phase 2:** Inbound protected alias (4.2) + on-platform replies via relay token Reply-To +
  inbound parser service + `msg.pentagon.games` subdomain.
- **Phase 3:** Agent-offered relay (Irene suggests/sends via the gated endpoint), richer threads.

---

## 12. Open questions for Idon

1. Default recipient policy: everyone-but-rate-limited vs friends-only? (I lean friends-only at
   launch, loosen later.)
2. Exact NPC prices for the four tiers in §7.
3. Phase 1 outbound-only acceptable, or do you want the inbound `+identity@` alias in v1 too?
4. Blocked-sender behavior: silent-drop (anti-probe) vs explicit reject?
5. Subdomain `msg.pentagon.games` now (cleaner) or stick with `+identity@` for v1?
