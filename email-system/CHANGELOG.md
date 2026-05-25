# Email Redesign — Handoff & Decision Log
**Asset:** "You just met Prof" referral/contact email
**Original:** `_TEST_V3__You_just_met_Prof.eml`
**Current:** `TEST_V6_You_just_met_Prof.eml`
**Format:** MIME multipart/alternative (.eml) — text/plain + text/html parts

---

## 1. Core intent of the redesign

The original V3 email was built as a **product/infra funnel** — it led with branding,
then pushed the recipient toward "build your own card", explore games, connect a wallet,
Pentagon Chain links, etc.

The redesign **re-scopes the email around a single job: sharing one person's contact info.**
Everything that promoted the platform/infrastructure was demoted or cut. The recipient
("you just met Prof") should walk away knowing how to reach Prof and, optionally, pay Prof.

**Priority hierarchy (highest → lowest):**
1. The person (Prof) and their contact channels
2. The primary action (Verify & Connect)
3. The wallet address (so the email doubles as a "pay me" card)
4. Brand / boilerplate (minimized footer only)

---

## 2. Change-by-change log with rationale

### 2.1 Logo
- **Before:** 160px wide, standalone banner at the very top, 20px bottom margin.
- **After:** 18px, moved into the footer, 70% opacity, paired inline with the
  "Pentagon Network Member" text.
- **Why:** The logo was the first and largest thing in the email — it emphasized the
  brand before the message. Brand is the *least* important element for this email's job.
  Shrinking to icon-scale (matching the X/Telegram row icons) and relocating to the
  footer makes it a quiet attribution mark, not a headline.

### 2.2 Removed the "build your own infra" content
- **Removed entirely:** the 3-card row ("Your Card" / "Explore" / "Own Wallet") that
  linked to pentagon.games/card, the games ecosystem, and EOA wallet connection.
- **Why:** This is platform self-promotion. It directly competes with the contact-sharing
  goal and adds 3 more tap targets pulling attention away from the person.

### 2.3 Rewards block — demoted, not deleted
- **Before:** A dedicated two-row card (EVM Mainnet Gas + 1,000 $PROF tokens) with icons
  and descriptions, occupying significant vertical space.
- **After:** Condensed into one supporting line of microcopy directly under the CTA button:
  "Verifying lets you connect as a friend — you'll also get free EVM gas and 1,000 $PROF tokens."
- **Why:** The rewards are a *reason to click*, not the subject of the email. They belong
  as CTA support copy, not as a standalone feature block.

### 2.4 Contact info — from floating pills to a structured list
- **Before:** Three rounded "pills" (X, Telegram, email) centered with no container.
  X and TG sat side-by-side, email wrapped to its own row below. They read as loose tags
  and reflowed inconsistently on mobile.
- **After:** A single bordered container with three full-width stacked rows. Each row has:
  an icon, a small uppercase label (X (Twitter) / Telegram / Email), the handle/value,
  and a right-aligned action affordance ("Open →" / "Mail →"). The entire row is a tap target.
- **Why:** This is the email's primary content and it looked unstructured. Full-width
  stacked rows render identically on desktop and mobile — nothing reflows or wraps oddly.
  It now reads as a proper contact card.

### 2.5 Wallet address — kept on the card, repositioned + relabeled
- **Before:** Wallet + QR sat high on the card, labeled only "EVM Wallet Address".
- **After:** Still inside the card (so it travels if the email is forwarded to pay Prof),
  but moved below the CTA. Relabeled "Send crypto to Prof — EVM Address" to make its
  purpose explicit. QR reduced from 108px to 76px.
- **Why:** The user explicitly wanted the address present "in case this is shared to pay me"
  — so it must stay on the card, not be cut. But it's lower priority than the contact
  channels, so it sits lower in the hierarchy. The relabel removes ambiguity about what
  the address is for.

### 2.6 Profile header — stripped to essentials
- **Before:** Avatar + "Prof" + "Pentagon Network Member" subtitle.
- **After:** Avatar + "Prof" only. "Pentagon Network Member" moved to the footer.
- **Why:** "Pentagon Network Member" is boilerplate/branding, not contact info. Removing it
  from the header keeps the focus on the person; it now lives quietly in the footer next
  to the small logo.

### 2.7 Spacing & dimensions — tightened
- Card width: 560px → 540px.
- Hero top padding reduced; inter-section padding trimmed throughout.
- Avatar: 84px → 76px.
- Outer page padding: 40px → 32px vertical.
- **Why:** The original had loose vertical rhythm that made the email feel long and
  unfocused. Tighter spacing makes it read as one cohesive card.

---

## 3. Known limitations / open items for the agent

### 3.1 Social icons (X, Telegram)
- The .eml currently uses generic Unicode glyphs: the mathematical-bold X character
  (&#120143;) for X, and an envelope glyph (&#9993;) for Telegram and email.
- **Reason:** Email clients do not reliably render icon webfonts (Tabler, Font Awesome,
  etc.). Inline SVG is also stripped by many clients (notably Gmail, Outlook).
- **To use true brand icons:** host PNG icon assets and swap the glyph `<td>` for an
  `<img>` tag. Recommended ~18-20px square PNGs on the existing brand-kit CDN.
- This is the single most likely thing to want fixing before production.

### 3.2 Footer logo aspect ratio
- The footer logo is forced to 18x18. If `alternative-logo-db.png` is a wide/horizontal
  lockup, it will be distorted at a square size.
- **Fix:** supply a square icon mark, OR set only `height="18"` and `width="auto"`,
  OR drop the logo and keep just the "Pentagon Network Member" text.

### 3.3 Avatar placeholder
- `src` points at `avatar-default.png` (a generic placeholder). For real sends, this
  must be populated per-recipient with Prof's actual photo.

### 3.4 Dynamic / templated fields
For productionizing, these values are per-recipient and should be template variables:
- Name "Prof" (appears in hero, profile, CTA, wallet label, plain-text part, subject)
- Handles: `x.com/nftprof`, `@nftprof`, `nftprof@pentagon.games`
- Wallet address: `0xE52dF2f14fDEa39f11a22284EA15a7bd7bf09eB8` (used twice: text + QR URL)
- Avatar image URL
- Verify link referral param: `?referral_username=Prof`
- QR is generated live via `api.qrserver.com` from the address — if that external
  dependency is unwanted, pre-generate and host the QR image instead.

### 3.5 Subject line
- Bumped V3 → V6 in the subject ("[TEST V6] You just met Prof") to track iterations.
- Production subject should drop the "[TEST V#]" prefix.

---

## 4. Build / packaging notes

- The .eml is assembled with Python's `email.mime` (multipart/alternative).
- Headers (From, To, Reply-To, Date) are copied verbatim from the original V3 file.
- Both parts are kept in sync: the text/plain part lists the same contact info and
  links as the HTML, for clients that don't render HTML.
- HTML is table-based with inline styles — the correct, intentional approach for email
  clients (do NOT refactor to divs/flexbox/external CSS; that breaks Outlook).
- `role="presentation"` is on all layout tables for accessibility.
- An mso conditional comment sets PixelsPerInch for Outlook rendering — keep it.

---

## 5. Version history
- **V3** — original (infra-funnel layout, large logo).
- **V4** — logo shrunk to 40px and moved to footer; infra cards cut; rewards condensed.
- **V5** — floating contact pills replaced with structured contact list; wallet relabeled
  as "Send crypto" block and moved below CTA.
- **V6** — "Pentagon Network Member" moved from profile header to footer; logo further
  reduced to 18px (icon-scale, matching contact-row icons).
