# Pentagon Email Infrastructure — Internal API Documentation

> Last updated: 2026-05-31 | Maintainer: Cerise01 (primary), Cerise02 (email-ops)

---

## Overview

All transactional and social emails for Pentagon Games are sent via **Gmail SMTP Relay** from `identity@pentagon.games`. This replaced Brevo (formerly Sendinblue) on March 29, 2026. There is zero cost, full control, and no third-party dependency for email sending.

**All other email systems are deprecated.** Only Gmail SMTP Relay is active.

---

## Architecture

```
User Action (signup/login/reset/NFC tap/friend approve)
    → Django view (views.py)
        → send_email() in gmail_email.py (transactional)
        → send_friend_email_v6() in gmail_email.py (friend contact)
            → Forks subprocess (non-blocking) [GCP]
            → Inline SMTP (synchronous) [AWS]
                → smtp-relay.gmail.com:587 (STARTTLS, IP-auth)
                    → Email delivered to user
```

---

## Active System: Gmail SMTP Relay

| Setting | Value |
|---------|-------|
| SMTP Host | `smtp-relay.gmail.com` |
| SMTP Port | `587` (STARTTLS) |
| Auth | IP-based (no password needed) |
| Whitelisted IPs | `13.212.154.41` (AWS pg-identity) |
| From Address | `identity@pentagon.games` |
| From Name | `Pentagon Identity` |
| Google Workspace Account | `identity@pentagon.games` (2FA enabled) |
| Admin Config | admin.google.com → Apps → Gmail → Routing → SMTP relay |
| Allowed Senders | Only addresses in pentagon.games domain |
| Require TLS | Yes |

### Server Details

| Component | Value |
|-----------|-------|
| Server | pg-identity-be (AWS: `13.212.154.41`) |
| SSH | `ssh ubuntu@13.212.154.41` |
| Service | supervisor → `pentagon-login-backend` |
| Workers | gunicorn, 7 workers (gevent), port 8031 |
| Nginx | `api.account.pentagon.games` → localhost:8031 |
| DB | PostgreSQL on `172.31.46.190:5432` (pg_identity_db) |
| Logs (gunicorn) | `/var/log/pentagon/pentagon-login-backend.err.log` |
| Logs (email) | `/var/log/pentagon/email-send.log` |

---

## Email Types

### Transactional (triggered by user action)

| Email Type | Trigger | Subject Pattern |
|------------|---------|-----------------|
| `verify_email` | New signup | "{Brand} \| Activate your account" |
| `verify_email_with_creds` | Signup with auto-generated creds | "{Brand} \| Activate your account" |
| `verify_email_ref` | Signup via referral | "{Brand} \| Activate your account" |
| `verify_email_with_creds_ref` | Signup with creds + referral | "{Brand} \| Activate your account" |
| `verify_email_with_creds_ref_code` | Signup with creds + ref + NFC code | "{Brand} \| Activate your account" |
| `auto_login` | Magic login link | "{Brand} \| Magic Link" |
| `auto_login_ref` | Magic login via referral | "{Brand} \| Magic Link" |
| `auto_login_ref_fr` | Magic login via friend ref | "{Brand} \| Magic Link" |
| `reset_password` | Password reset request | "{Brand} \| Reset Password" |

### Friend Contact Email (V6 — NFC/social flow)

| Variant | Trigger | Subject |
|---------|---------|---------|
| `new_user` | Recipient has no PG account | "You just met {username}" |
| `existing_user` | Recipient has PG account, not friends | "{username} wants to connect" |
| `existing_friend` | Already friends | "{username}'s contact info" |

Auto-detected by `_detect_state()` — checks `UserFriendship` table and user verification status.

---

## Brand System

Emails are brand-aware. The brand is determined by `user_from_key` passed during signup, stored in `PentagonEmailConfig` DB table.

| Brand Key | Brand Name | Site |
|-----------|-----------|------|
| `gunnies` | Gunnies | gunnies.io |
| `penxr` | PenXR | penxr.io |
| `pentagon` | Pentagon Games | pentagon.games |
| `bcsh` | BCSH | bcsh.xyz |
| `pg-wallet` | Pentagon Games | pentagon.games |

Subject lines and callback URLs are stored in the `pentagon_email_config` table:
```sql
SELECT user_from_key, email_type, callback_url, subject
FROM pentagon_email_config
ORDER BY user_from_key, email_type;
```

---

## How to Request a New Email Type

### Step 1: Define the email
- **Email type slug** (e.g., `welcome_back`, `referral_reward`)
- **Trigger** — what user action fires it
- **Subject line** per brand
- **Callback URL** — where the link in the email points
- **Template** — plain text body (transactional) or HTML (campaign/social)

### Step 2: Add DB config
```sql
INSERT INTO pentagon_email_config (user_from_key, email_type, callback_url, subject)
VALUES ('pentagon', 'welcome_back', 'https://pentagon.games/welcome?key=***', 'Pentagon Games | Welcome Back');
```
Repeat for each brand that needs it.

### Step 3: Add code
1. Add a body builder function in `gmail_email.py`:
   ```python
   def _body_welcome_back(link, brand, **kw):
       return f"Hi {kw.get('username', '')},\n\nWelcome back to {brand['brand_name']}!..."
   ```
2. Register it in the `BUILDERS` dict:
   ```python
   BUILDERS = {
       ...
       "welcome_back": _body_welcome_back,
   }
   ```
3. Call `send_email()` from the relevant view:
   ```python
   send_email(email_type="welcome_back", to=user.email, token=token, user_from_key=user_from, username=user.username)
   ```

### Step 4: Deploy
```bash
ssh ubuntu@13.212.154.41
# Edit files
sudo supervisorctl stop pentagon-login-backend
sudo pkill -9 -f gunicorn
sudo rm -rf /var/www/pentagon/prod/pentagon-login-backend/user/__pycache__
sudo supervisorctl start pentagon-login-backend
```

### Step 5: Test
```bash
# On pg-identity server
cd /var/www/pentagon/prod/pentagon-login-backend
source venv/bin/activate
python3 -c "
from user.gmail_email import _send_email_impl
_send_email_impl('welcome_back', 'test@example.com', 'test-token', 'pentagon', username='TestUser')
"
```

---

## Multi-Account Email Access (Corporate)

Pentagon Games uses **Google Workspace** for corporate email. All accounts are on the `pentagon.games` domain.

### Accounts

| Account | Purpose | Access |
|---------|---------|--------|
| `nftprof@pentagon.games` | CEO / primary | gog CLI, browser |
| `identity@pentagon.games` | SMTP relay sender | IP-auth only, no inbox access needed |
| `admin@pentagon.games` | Admin / ATS | gog CLI |
| `dipak@bcsh.io` | GCP org admin | Dipak's access |

### Agent Access (via `gog` CLI)

Cerise02 manages email triage via the `gog` CLI (Google Workspace CLI):
```bash
# Search emails
gog gmail search 'from:github newer_than:1d' --account nftprof@pentagon.games

# Read email
gog gmail read <message_id> --account nftprof@pentagon.games

# Send email
gog gmail send --to recipient@example.com --subject "Subject" --body "Body" --account nftprof@pentagon.games
```

OAuth tokens expire every 7 days (Testing mode). Re-auth when needed.

### Discord Channels for Email Requests
- **#email-infrastructure** (`1488005740902875198`) — system config, SMTP, templates
- **#email-ops** — triage, send requests, campaign coordination

---

## NFC → Email → Onboarding Flow

The most important email flow. One NFC tap onboards a user to blockchain.

```
NFC Card Tap
    → Phone opens creator's profile page (pentagon.games/u/{username})
    → Visitor enters email on the page
    → Backend: POST /user/signup (with referral_username + nfc_code)
        → If new user: account auto-created, AA wallet generated, PC gas sent
        → Email sent: "You just met {username}" (V6 template)
    → User clicks "Verify & Connect" in email
        → Email verified, friend request auto-accepted
        → SocialFi token sent (if creator has one)
        → User lands on their dashboard
```

### What the user gets (behind the scenes):
1. Pentagon account with AA custodial wallet
2. PC gas on their AA wallet (mainnet gas)
3. Auto-friended with NFC card owner
4. Creator's SocialFi token (if applicable)

### Email psychology:
- Don't reveal account was already created
- Frame it as "you met someone, here's their info"
- Clicking verifies email and connects them
- Reciprocal: completing your profile gives the creator YOUR contact info

---

## Deprecated Email Systems

### Brevo (formerly Sendinblue) — DEPRECATED 2026-03-29

| Detail | Value |
|--------|-------|
| Status | **FULLY DEPRECATED** |
| Reason | IP whitelist issues, no admin access, third-party dependency |
| Replaced by | Gmail SMTP Relay |
| Migration date | March 29, 2026 |
| Backup code | `user/utils.py.bak.20260330` on pg-identity server |
| AWS IP issue | `13.212.154.41` was never whitelisted at app.brevo.com |

**Do not use Brevo.** The API key may still be in `.env` files but the IP is not whitelisted and Brevo is not the active email path. If you see `BREVO_API_KEY` in a config, ignore it.

**To rollback (emergency only):**
```bash
sudo cp /var/www/pentagon/prod/pentagon-login-backend/user/utils.py.bak.20260330 \
       /var/www/pentagon/prod/pentagon-login-backend/user/utils.py
sudo supervisorctl restart pentagon-login-backend
```
Note: Brevo IP whitelist must be fixed first for rollback to work.

### Mailgun — DEPRECATED (Legacy)

DNS records for Mailgun still exist on `pentagon.games` and `chainguardians.io`:
- `email.mg.pentagon.games` CNAME → `mailgun.org`
- `mg.pentagon.games` MX → `mxa.mailgun.org` / `mxb.mailgun.org`
- `mg.pentagon.games` TXT → `v=spf1 include:mailgun.org ~all`

These are **dead DNS records** from the original ChainGuardians era. Mailgun is not active and has not been used since before the Pentagon Games rebrand. The records can be cleaned up but are harmless.

### SendGrid — Never Used

No SendGrid configuration exists anywhere in Pentagon infrastructure.

### Mandrill / Mailchimp — Never Used

No configuration exists.

---

## Code Files

| File | Location | Purpose |
|------|----------|---------|
| `gmail_email.py` | `/var/www/pentagon/prod/pentagon-login-backend/user/` | All email logic: templates, SMTP send, friend email |
| `utils.py` | Same path | Imports `send_email` from gmail_email (also has inline SMTP for AWS) |
| `utils.py.bak.20260330` | Same path | Backup of original Brevo API code |
| `tasks.py` | Same path | Celery tasks, friend approval flow |
| `views.py` | Same path | API endpoints that trigger emails |
| `models.py` | Same path | `PentagonEmailConfig` model, `UserFriendship` model |

---

## Common Operations

### Restart email service
```bash
ssh ubuntu@13.212.154.41
sudo supervisorctl stop pentagon-login-backend
sudo pkill -9 -f gunicorn
sudo rm -rf /var/www/pentagon/prod/pentagon-login-backend/user/__pycache__
sudo supervisorctl start pentagon-login-backend
```

### Check email logs
```bash
ssh ubuntu@13.212.154.41
sudo tail -f /var/log/pentagon/pentagon-login-backend.err.log  # gunicorn
cat /var/log/pentagon/email-send.log  # email subprocess errors
```

### Test email manually
```bash
ssh ubuntu@13.212.154.41
cd /var/www/pentagon/prod/pentagon-login-backend
# For transactional:
# Use the Python test snippet from "How to Request" section above

# For friend email V6:
# Pass creator_id and friend_id from the user table
```

### Check SMTP connectivity
```bash
ssh ubuntu@13.212.154.41
python3 -c "
import smtplib
s = smtplib.SMTP('smtp-relay.gmail.com', 587)
s.ehlo(); s.starttls(); s.ehlo()
print('SMTP OK')
s.quit()
"
```

---

## History

| Date | Change |
|------|--------|
| Pre-2026 | Mailgun used for ChainGuardians era emails |
| Unknown | Brevo (Sendinblue) became primary transactional email |
| 2026-03-29 | Migrated from Brevo API to Gmail SMTP Relay |
| 2026-03-29 | Fixed DB_HOST, DB permissions for email subprocess |
| 2026-04-03 | Fixed subprocess `__main__` handler (emails silently dropped) |
| 2026-04-05 | Updated verify emails to mention 72-hour expiry |
| 2026-04-15 | Added friend-approved HTML email (V1) with profile, QR, token |
| 2026-04-15 | Batch sent to 7 existing friends |
| 2026-04-19 | Migrated pen-wallet-backend email, added 35.225.2.90 to relay |
| 2026-04-24 | Fixed email on AWS pg-identity (stale pyc + venv conflicts) |
| 2026-04-24 | Switched to inline SMTP on AWS (subprocess approach broken) |
| 2026-05-25 | Friend email redesigned to V6 (person-first, 3 variants) |

---

## Campaign Email Standards

### Standard Header Format

All campaign/marketing emails MUST use this standard header:

```html
<!-- HEADER -->
<div style="padding:28px 36px 24px;border-bottom:1px solid #1a1a28;background:#0a0a10;">
  <img src="https://pentagon.games/assets/images/brand-kit/alternative/png/alternative-logo-ow.png"
       alt="Pentagon Games" style="height:30px;width:auto;display:block;" />
</div>
```

**Rules:**
- Dark background (`#0a0a10`)
- Logo left-aligned, 30px height
- Use the hosted PNG logo, NOT an SVG or base64-encoded image
- Light logo (`alternative-logo-ow.png`) for dark backgrounds
- Dark logo (`alternative-logo-db.png`) for light backgrounds
- Border bottom separator (`1px solid #1a1a28`)

### Image Hosting — CRITICAL

**NEVER use base64/data URI images in email templates.**

Most email clients (Gmail, Outlook, Yahoo, Apple Mail) block or limit base64 `data:image/...` URIs. This is why the "first email always has broken images."

**Always host images on `pentagon.games` and reference them by URL:**

```html
<!-- ✅ CORRECT — hosted image URL -->
<img src="https://pentagon.games/assets/images/brand-kit/alternative/png/alternative-logo-ow.png"
     alt="Pentagon Games" style="height:30px;width:auto;display:block;" />

<!-- ❌ WRONG — base64 data URI (WILL break in email clients) -->
<img src="data:image/png;base64,iVBORw0KGgoAAAANSU..." />
```

**Available brand kit images (hosted):**

| Image | URL |
|-------|-----|
| Logo (light/dark bg) | `https://pentagon.games/assets/images/brand-kit/alternative/png/alternative-logo-ow.png` |
| Logo (dark/light bg) | `https://pentagon.games/assets/images/brand-kit/alternative/png/alternative-logo-db.png` |
| NPC icon | Must be uploaded to `pentagon.games/assets/images/email/` |
| PC icon | Must be uploaded to `pentagon.games/assets/images/email/` |
| Campaign screenshots | Must be uploaded to `pentagon.games/assets/images/email/` |

**For new images:** Upload them to the pentagon.games frontend server (`18.139.44.212`) under `/var/www/prod/public/assets/images/email/` and reference as `https://pentagon.games/assets/images/email/<filename>`.

### Personalization Variables

| Variable | Source | Use |
|----------|--------|-----|
| `{{username}}` | VIP DB / pg-identity user table | Greeting: "Hey {{username}}," |
| `{unsubscribe_link}` | Auto-generated JWT by `send_email()` | Footer unsubscribe link |
| `{{email}}` | User's email | Footer: "Sent to {{email}} as an early supporter" |

### Unsubscribe Link — IMPORTANT

The unsubscribe page expects a **JWT token** as the `key` parameter:

```
✅ https://pentagon.games/unsubscribe?key=<JWT_TOKEN>
❌ https://pentagon.games/unsubscribe?email={{email}}  ← WILL ALWAYS FAIL
```

**How it works in the backend pipeline (`gmail_email.py`):**
1. `send_email()` calls `_generate_unsubscribe_token(to_email)`
2. Looks up user by email, creates 90-day JWT: `{"id": user.id, "type": "unsubscribe"}`
3. Builds URL: `https://pentagon.games/unsubscribe?key=<TOKEN>`
4. Replaces `{unsubscribe_link}` in HTML template
5. Adds `List-Unsubscribe` header for email client one-click unsubscribe

**For manual sends (via gog CLI or scripts):**
```python
# On pg-identity server, Django shell:
from user.gmail_email import _generate_unsubscribe_token
token = _generate_unsubscribe_token("user@example.com")
# Then use: https://pentagon.games/unsubscribe?key={token}
```

### Standard Footer Format

```html
<!-- FOOTER -->
<div style="padding:28px 36px;border-top:1px solid #1a1a28;background:#060610;text-align:center;">
  <p style="color:#555577;font-size:12px;margin:0 0 8px;">
    Sent to {{email}} as an early Pentagon supporter.
  </p>
  <p style="color:#555577;font-size:12px;margin:0;">
    <a href="{unsubscribe_link}" style="color:#777799;text-decoration:underline;">Unsubscribe</a>
  </p>
  <div style="margin:16px 0 0;">
    <a href="https://x.com/PentagonGamesXP" style="color:#777799;text-decoration:none;margin:0 8px;">𝕏</a>
    <a href="https://discord.gg/pentagongamesxp" style="color:#777799;text-decoration:none;margin:0 8px;">Discord</a>
    <a href="https://t.me/pentagongamesxp" style="color:#777799;text-decoration:none;margin:0 8px;">Telegram</a>
  </div>
</div>
```

**Social links (ALWAYS use these exact URLs):**
- X/Twitter: `https://x.com/PentagonGamesXP`
- Discord: `https://discord.gg/pentagongamesxp`
- Telegram: `https://t.me/pentagongamesxp`

**DO NOT use** `@PentagonGames`, `pentagonchain`, or any other handle. It's always `pentagongamesxp`.

---

## Standard Email Header

All Pentagon Games emails must use a consistent dark-themed header with the **hosted PNG logo** (not base64/SVG).

### Header HTML

```html
<!-- HEADER -->
<div style="padding:28px 36px 24px;border-bottom:1px solid #1a1a28;background:#0a0a10;">
  <img src="https://pentagon.games/assets/images/brand-kit/alternative/png/alternative-logo-ow.png"
       alt="Pentagon Games"
       style="height:30px;width:auto;display:block;" />
</div>
```

### Header Specifications

| Property | Value |
|----------|-------|
| Background color | `#0a0a10` |
| Bottom border | `1px solid #1a1a28` |
| Padding | `28px 36px 24px` |
| Logo source | `https://pentagon.games/assets/images/brand-kit/alternative/png/alternative-logo-ow.png` |
| Logo format | PNG (white on transparent, for dark backgrounds) |
| Logo height | `30px` |
| Logo alignment | Left-aligned |

**IMPORTANT:** Do NOT use base64-encoded images or SVG format in email headers. See "Image Best Practices" below.

---

## Unsubscribe Process

Pentagon Games uses a **JWT-based unsubscribe** system for CAN-SPAM / GDPR compliance.

### How It Works

1. The backend `send_email()` function in `user/gmail_email.py` auto-generates a JWT unsubscribe token for each recipient.
2. The email template uses the `{unsubscribe_link}` merge variable.
3. The backend replaces `{unsubscribe_link}` with the full URL: `https://pentagon.games/unsubscribe?key=<JWT_TOKEN>`
4. The backend also adds a `List-Unsubscribe` header for one-click unsubscribe (RFC 8058).

### Correct Unsubscribe Link Format

**DO:** Use `{unsubscribe_link}` in templates — the backend handles the rest.

```html
<a href="{unsubscribe_link}" style="color:#444466;text-decoration:underline;">Unsubscribe</a>
```

**DO NOT:** Use `?email={{email}}` — this was the old, insecure format.

### Manual Token Generation

If sending emails outside the pipeline (e.g., via `gog` CLI), generate the JWT manually:

```bash
ssh ubuntu@13.212.154.41
cd /var/www/pentagon/prod/pentagon-login-backend
source venv/bin/activate
python3 -c "
from user.gmail_email import generate_unsubscribe_token
token = generate_unsubscribe_token(email='user@example.com')
print(f'https://pentagon.games/unsubscribe?key={token}')
"
```

---

## Image Best Practices

Email clients aggressively filter inline images. Follow these rules for reliable image delivery.

### Rules

1. **ALWAYS use hosted images via HTTPS URLs.** Never use `data:` URIs or base64-encoded images.
2. **Use PNG format.** SVG is blocked or stripped by most email clients (Gmail, Outlook, Yahoo).
3. **Host all images on `pentagon.games` or a CDN** with HTTPS.
4. **Always include `alt` text** on every `<img>` tag.
5. **Keep images under 100KB each.**
6. **Set explicit `height` and/or `width`** to prevent layout shifts.

### Why NOT base64 / `data:` URIs?

- **Gmail** strips or blocks `data:` URI images on first delivery.
- **Outlook** blocks base64 inline images by default.
- **Yahoo Mail** may strip them entirely.
- **SVG format** is actively blocked by most major email clients for security reasons.
- This causes "broken image" icons on first email delivery, damaging brand trust.

### Standard Pentagon Logo for Email

| Property | Value |
|----------|-------|
| URL | `https://pentagon.games/assets/images/brand-kit/alternative/png/alternative-logo-ow.png` |
| Format | PNG (white on transparent) |
| Height | `30px` |
| Alt text | `Pentagon Games` |

### Image Tag Template

```html
<img src="https://pentagon.games/assets/images/[path]"
     alt="[Descriptive alt text]"
     style="height:[X]px;width:auto;display:block;" />
```

---

## Related

- [pg-identity project docs](../index.html)
- [Standard Email Header & Footer Reference](../../crm/email-templates/STANDARD-HEADER.md)
- Obsidian vault: `infrastructure/email-system.md`
- Obsidian vault: `infrastructure/email-infrastructure-guide.md`
- Server details: `infrastructure/aws-servers.md`
