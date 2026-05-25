"""
Friend Contact Email V6 — Production template.
Drop-in replacement for _send_friend_approved_impl() in gmail_email.py.

Design: V6 "You just met {username}" — person-first, platform-last.
Three variants auto-detected by recipient state:
  1. new_user     — not a PG member (strongest CTA: verify & connect)
  2. existing_user — has PG account, not yet friends (log in & connect)
  3. existing_friend — already friends (contact card, no action needed)

Uses username (e.g. "nftprof"), not display name.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp-relay.gmail.com"
SMTP_PORT = 587
FROM_EMAIL = "identity@pentagon.games"
FROM_NAME = "Pentagon Identity"
LOGO_URL = "https://pentagon.games/assets/images/brand-kit/alternative/png/alternative-logo-db.png"
DEFAULT_AVATAR = "https://storage.googleapis.com/pgpublic-access/email-assest/avatar-default.png"


def _detect_state(creator, friend):
    """Detect recipient's relationship to Pentagon + creator."""
    from user.models import UserFriendship
    from django.db.models import Q

    is_pg_user = bool(friend.id and friend.username and friend.verified)
    if not is_pg_user:
        return "new_user"

    are_friends = UserFriendship.objects.filter(
        Q(user1=creator, user2=friend) | Q(user1=friend, user2=creator),
        status="accepted"
    ).exists()

    return "existing_friend" if are_friends else "existing_user"


def _get_creator_data(creator):
    """Extract all display data from creator."""
    ed = creator.extra_data
    ec = getattr(creator, "echovault_contract", None)
    pd = creator.penxr_data
    pic = getattr(pd, "profile_picture", "") if pd else ""
    if not pic:
        pic = DEFAULT_AVATAR

    return {
        "un": creator.username,
        "pic": pic,
        "addr": creator.mm_address or "",
        "x": getattr(ed, "twitter_username", "") if ed else "",
        "tg": getattr(ed, "telegram_username", "") if ed else "",
        "li": getattr(ed, "linkedin_username", "") if ed else "",
        "email": creator.email or "",
        "has_token": bool(ec and getattr(ec, "symbol", None)),
        "token": getattr(ec, "symbol", "") if ec else "",
    }


# ─── HTML building blocks ─────────────────────────────────────────

def _contact_row(href, icon, label, value, action="Open"):
    """Single contact list row."""
    return f"""<tr><td style="padding:14px 18px; border-bottom:1px solid #eef0f2;">
  <a href="{href}" style="text-decoration:none; display:block;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td width="28" style="vertical-align:middle; color:#111827; font-size:16px;">{icon}</td>
      <td style="vertical-align:middle; padding-left:6px;">
        <p style="color:#9ca3af; margin:0; font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.8px;">{label}</p>
        <p style="color:#111827; margin:1px 0 0; font-size:14px; font-weight:600; word-break:break-all;">{value}</p>
      </td>
      <td style="vertical-align:middle; text-align:right; color:#4f46e5; font-size:13px; font-weight:600;">{action} &#8594;</td>
    </tr></table>
  </a>
</td></tr>"""


def _contact_row_last(href, icon, label, value, action="Mail"):
    """Last contact row (no bottom border)."""
    return f"""<tr><td style="padding:14px 18px;">
  <a href="{href}" style="text-decoration:none; display:block;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td width="28" style="vertical-align:middle; color:#111827; font-size:16px;">{icon}</td>
      <td style="vertical-align:middle; padding-left:6px;">
        <p style="color:#9ca3af; margin:0; font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.8px;">{label}</p>
        <p style="color:#111827; margin:1px 0 0; font-size:14px; font-weight:600; word-break:break-all;">{value}</p>
      </td>
      <td style="vertical-align:middle; text-align:right; color:#4f46e5; font-size:13px; font-weight:600;">{action} &#8594;</td>
    </tr></table>
  </a>
</td></tr>"""


def _contact_list(d):
    """Build contact list from creator data."""
    rows = []
    if d["x"]:
        rows.append(("https://x.com/" + d["x"], "&#120143;", "X (Twitter)", "x.com/" + d["x"], "Open"))
    if d["tg"]:
        rows.append(("https://t.me/" + d["tg"], "&#9993;", "Telegram", "@" + d["tg"], "Open"))
    if d["li"]:
        rows.append(("https://linkedin.com/in/" + d["li"], "&#128279;", "LinkedIn", d["li"], "Open"))
    if d["email"]:
        rows.append(("mailto:" + d["email"], "&#9993;&#65039;", "Email", d["email"], "Mail"))

    if not rows:
        return ""

    html_rows = ""
    for i, (href, icon, label, value, action) in enumerate(rows):
        if i == len(rows) - 1:
            html_rows += _contact_row_last(href, icon, label, value, action)
        else:
            html_rows += _contact_row(href, icon, label, value, action)

    return f"""<tr><td style="padding:18px 32px 4px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fafafa; border-radius:12px; border:1px solid #e5e7eb;">
    {html_rows}
  </table>
</td></tr>"""


def _wallet_block(d):
    """Wallet / pay-me block."""
    if not d["addr"]:
        return ""
    qr = f"https://api.qrserver.com/v1/create-qr-code/?size=160x160&data={d['addr']}&bgcolor=fafafa&color=111827"
    return f"""<tr><td style="padding:14px 32px 4px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fafafa; border-radius:12px; border:1px solid #e5e7eb;">
  <tr><td style="padding:18px 20px;">
    <p style="color:#9ca3af; margin:0 0 8px; font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:1px;">Send crypto to {d['un']} &mdash; EVM Address</p>
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="vertical-align:middle; padding-right:16px;">
        <p style="color:#111827; margin:0; font-size:12px; font-family:'SF Mono',Consolas,monospace; word-break:break-all; line-height:1.6;">{d['addr']}</p>
      </td>
      <td width="84" style="vertical-align:middle; text-align:right;">
        <img src="{qr}" alt="Wallet QR" width="76" height="76" style="border-radius:8px; border:1px solid #e5e7eb; display:block;">
      </td>
    </tr></table>
  </td></tr></table>
</td></tr>"""


def _footer(reason):
    return f"""<tr><td style="padding:22px 32px; border-top:1px solid #e5e7eb;">
  <table width="100%" cellpadding="0" cellspacing="0">
  <tr><td style="text-align:center;">
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto 8px;">
    <tr>
      <td style="vertical-align:middle; padding-right:6px;">
        <img src="{LOGO_URL}" alt="Pentagon" width="18" height="18" style="display:block; opacity:0.7;">
      </td>
      <td style="vertical-align:middle;">
        <span style="color:#6b7280; font-size:12px; font-weight:600;">Pentagon Network Member</span>
      </td>
    </tr>
    </table>
    <p style="color:#9ca3af; font-size:11px; margin:0; line-height:1.6;">{reason}</p>
  </td></tr></table>
</td></tr>"""


def _shell(title, preheader, body_rows):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
<title>{title}</title>
</head>
<body style="margin:0; padding:0; background-color:#f4f4f7; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif; -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%;">
<div style="display:none; max-height:0; overflow:hidden; mso-hide:all;">
  {preheader}
  &nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;
</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f7; padding:32px 16px;">
<tr><td align="center">
<table role="presentation" width="540" cellpadding="0" cellspacing="0" style="width:100%; max-width:540px; background-color:#ffffff; border-radius:16px; overflow:hidden; border:1px solid #e5e7eb; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
{body_rows}
</table>
</td></tr></table>
</body>
</html>"""


# ─── Variant builders ──────────────────────────────────────────────

def _build_new_user(d):
    """New user: strongest CTA, verify & connect."""
    un = d["un"]
    verify = f"https://id.peg.gg?referral_username={un}&verify=1"
    token_line = f" and 1,000 ${d['token']} tokens" if d["has_token"] else ""

    hero = f"""<tr><td style="padding:36px 32px 8px; text-align:center;">
  <h1 style="color:#111827; margin:0 0 10px; font-size:24px; font-weight:800; line-height:1.3;">You just met {un}</h1>
  <p style="color:#4b5563; margin:0; font-size:14px; line-height:1.7; max-width:420px; display:inline-block;">
    Here's <strong>{un}</strong>'s contact info so you can stay connected.
  </p>
</td></tr>"""

    profile = f"""<tr><td style="padding:22px 32px 0; text-align:center;">
  <img src="{d['pic']}" alt="{un}" width="76" height="76" style="border-radius:50%; border:3px solid #e5e7eb; margin-bottom:12px; display:inline-block; object-fit:cover;">
  <h2 style="color:#111827; margin:0; font-size:19px; font-weight:800;">{un}</h2>
</td></tr>"""

    cta = f"""<tr><td style="padding:18px 32px 6px; text-align:center;">
  <a href="{verify}" style="display:inline-block; background:#4f46e5; color:#ffffff; padding:15px 38px; border-radius:12px; text-decoration:none; font-size:15px; font-weight:700; letter-spacing:0.3px; mso-padding-alt:0;">Verify &amp; Connect with {un} &#8594;</a>
  <p style="color:#9ca3af; margin:12px 0 0; font-size:12px; line-height:1.6;">
    Verifying lets you connect as a friend &mdash; you'll also get free EVM gas{token_line}.
  </p>
</td></tr>"""

    return {
        "subject": f"You just met {un}",
        "preheader": f"You just met {un}. Here's how to stay in touch and connect.",
        "body": hero + profile + _contact_list(d) + cta + _wallet_block(d) + _footer(f"You received this because you met {un} and shared your email."),
    }


def _build_existing_user(d):
    """Existing user: log in to connect."""
    un = d["un"]
    login = f"https://pentagon.games/login?referral_username={un}"
    verify = f"https://id.peg.gg?referral_username={un}&verify=1"
    token_line = f" and 1,000 ${d['token']} tokens" if d["has_token"] else ""

    hero = f"""<tr><td style="padding:36px 32px 8px; text-align:center;">
  <h1 style="color:#111827; margin:0 0 10px; font-size:24px; font-weight:800; line-height:1.3;">{un} wants to connect</h1>
  <p style="color:#4b5563; margin:0; font-size:14px; line-height:1.7; max-width:420px; display:inline-block;">
    Here's <strong>{un}</strong>'s contact info. Log in to accept the connection and update your settings.
  </p>
</td></tr>"""

    profile = f"""<tr><td style="padding:22px 32px 0; text-align:center;">
  <img src="{d['pic']}" alt="{un}" width="76" height="76" style="border-radius:50%; border:3px solid #e5e7eb; margin-bottom:12px; display:inline-block; object-fit:cover;">
  <h2 style="color:#111827; margin:0; font-size:19px; font-weight:800;">{un}</h2>
</td></tr>"""

    cta = f"""<tr><td style="padding:18px 32px 6px; text-align:center;">
  <a href="{login}" style="display:inline-block; background:#4f46e5; color:#ffffff; padding:15px 38px; border-radius:12px; text-decoration:none; font-size:15px; font-weight:700; letter-spacing:0.3px; mso-padding-alt:0;">Log In &amp; Connect with {un} &#8594;</a>
  <p style="color:#9ca3af; margin:12px 0 0; font-size:12px; line-height:1.6;">
    Connecting auto-accepts the friend request &mdash; you'll also get free EVM gas{token_line}.
  </p>
</td></tr>"""

    secondary = f"""<tr><td style="padding:8px 32px 0; text-align:center;">
  <p style="color:#9ca3af; margin:0; font-size:12px;">
    Don't have an account? <a href="{verify}" style="color:#4f46e5; font-weight:600; text-decoration:none;">Get your Pentagon ID &#8594;</a>
  </p>
</td></tr>"""

    vip = f"""<tr><td style="padding:10px 32px 4px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fafafa; border-radius:12px; border:1px solid #e5e7eb;">
  <tr><td style="padding:14px 18px;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="vertical-align:middle;">
        <p style="color:#111827; margin:0 0 2px; font-size:13px; font-weight:700;">Become a VIP Member</p>
        <p style="color:#9ca3af; margin:0; font-size:12px; line-height:1.5;">Earn referral rewards, exclusive drops, and priority access.</p>
      </td>
      <td width="80" style="vertical-align:middle; text-align:right;">
        <a href="https://vip.pentagon.games" style="color:#4f46e5; font-size:13px; font-weight:600; text-decoration:none;">Get VIP &#8594;</a>
      </td>
    </tr></table>
  </td></tr></table>
</td></tr>"""

    return {
        "subject": f"{un} wants to connect",
        "preheader": f"{un} shared their contact info with you. Log in to connect.",
        "body": hero + profile + _contact_list(d) + cta + secondary + vip + _wallet_block(d) + _footer(f"You received this because {un} shared their profile with you."),
    }


def _build_existing_friend(d):
    """Existing friend: contact card, no action needed."""
    un = d["un"]
    token_line = ""
    if d["has_token"]:
        token_line = f"""<tr><td style="padding:14px 32px 4px; text-align:center;">
  <p style="color:#9ca3af; margin:0; font-size:12px; line-height:1.6;">
    You received <strong style="color:#059669;">1,000 ${d['token']}</strong> from {un}'s personal SocialFi token.
  </p>
</td></tr>"""

    hero = f"""<tr><td style="padding:36px 32px 8px; text-align:center;">
  <h1 style="color:#111827; margin:0 0 10px; font-size:24px; font-weight:800; line-height:1.3;">Here's {un}'s contact info</h1>
  <p style="color:#4b5563; margin:0; font-size:14px; line-height:1.7; max-width:420px; display:inline-block;">
    You and <strong>{un}</strong> are already friends. Here are their latest details.
  </p>
</td></tr>"""

    profile = f"""<tr><td style="padding:22px 32px 0; text-align:center;">
  <div style="display:inline-block; background:#ecfdf5; color:#059669; padding:5px 12px; border-radius:20px; font-size:11px; font-weight:700; margin-bottom:14px; border:1px solid #a7f3d0;">&#10003; Already Friends</div><br>
  <img src="{d['pic']}" alt="{un}" width="76" height="76" style="border-radius:50%; border:3px solid #e5e7eb; margin-bottom:12px; display:inline-block; object-fit:cover;">
  <h2 style="color:#111827; margin:0; font-size:19px; font-weight:800;">{un}</h2>
</td></tr>"""

    return {
        "subject": f"{un}'s contact info",
        "preheader": f"Here's {un}'s contact info again. You're already connected.",
        "body": hero + profile + _contact_list(d) + token_line + _wallet_block(d) + _footer(f"You received this because you and {un} are friends on Pentagon Network."),
    }


# ─── Main entry point ─────────────────────────────────────────────

def send_friend_email_v6(creator_id, friend_id, tx_hash=""):
    """
    V6 friend contact email. Drop-in replacement for _send_friend_approved_impl().
    Auto-detects recipient state and sends the appropriate variant.
    """
    from user.models import User

    creator = User.objects.get(id=creator_id)
    friend = User.objects.get(id=friend_id)

    if not friend.email:
        logger.warning("Friend %s has no email, skipping", friend_id)
        return

    state = _detect_state(creator, friend)
    d = _get_creator_data(creator)

    if state == "new_user":
        parts = _build_new_user(d)
    elif state == "existing_user":
        parts = _build_existing_user(d)
    else:
        parts = _build_existing_friend(d)

    html = _shell(parts["subject"], parts["preheader"], parts["body"])

    # Plain text fallback
    plain = f"{parts['subject']}\n\n{parts['preheader']}\n\n"
    plain += f"Contact info for {d['un']}:\n"
    if d["x"]: plain += f"  X: x.com/{d['x']}\n"
    if d["tg"]: plain += f"  Telegram: @{d['tg']}\n"
    if d["email"]: plain += f"  Email: {d['email']}\n"
    if d["addr"]: plain += f"  EVM: {d['addr']}\n"
    plain += f"\nVerify: https://id.peg.gg?referral_username={d['un']}&verify=1\n"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = parts["subject"]
    msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg["To"] = friend.email
    msg["Reply-To"] = FROM_EMAIL
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.sendmail(FROM_EMAIL, [friend.email], msg.as_string())

    logger.info(
        "Friend email V6 sent: to=%s from=%s state=%s token=%s",
        friend.email, d["un"], state, d["token"] or "none"
    )
