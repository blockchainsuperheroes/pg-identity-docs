# Pentagon Email Infrastructure — Internal API Documentation

> Last updated: 2026-05-25 | Maintainer: Cerise01 (primary), Cerise02 (email-ops)

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

## Related

- [pg-identity project docs](../index.html)
- Obsidian vault: `infrastructure/email-system.md`
- Obsidian vault: `infrastructure/email-infrastructure-guide.md`
- Server details: `infrastructure/aws-servers.md`
