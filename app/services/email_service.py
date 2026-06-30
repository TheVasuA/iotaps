"""Transactional email service (SMTP) for platform notifications.

Sends branded HTML emails for account/device/billing lifecycle events:

    - device registered / device deleted
    - payment succeeded / payment failed
    - subscription expiring soon ("low days") / expired
    - welcome
    - generic alert emails (consumed by the Notification_Sender worker)

Design notes:
  * **Safe by default.** When SMTP is not configured (``smtp_host`` empty) every
    send becomes a logged no-op, so development/tests never attempt a live
    connection. Sends are wrapped so a failure NEVER propagates into the request
    or worker that triggered them — email is best-effort, not on the critical
    path.
  * **Stdlib only.** Uses ``smtplib`` + ``email.message`` run in a worker thread
    via ``asyncio.to_thread`` (no extra dependency). Port 465 → implicit SSL;
    otherwise STARTTLS when ``smtp_use_tls`` is set.
  * **One HTML layout.** :func:`_layout` wraps every message in a consistent
    branded shell so all notifications look the same.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.user import User

logger = get_logger(__name__)

# How long to wait on the SMTP exchange before giving up (seconds).
_SMTP_TIMEOUT = 20

ROLE_PROJECT_CENTER = "project_center"


# ---------------------------------------------------------------------------
# HTML layout
# ---------------------------------------------------------------------------
def _layout(
    *,
    heading: str,
    intro: str,
    rows: Sequence[tuple[str, str]] | None = None,
    note: str | None = None,
    cta_label: str | None = None,
    cta_url: str | None = None,
    accent: str = "#4f46e5",
) -> str:
    """Render a branded HTML email body.

    ``rows`` is an optional list of (label, value) detail pairs shown in a
    table; ``cta_*`` renders a call-to-action button. Kept dependency-free and
    inline-styled so it survives email clients that strip <style> blocks.
    """
    settings = get_settings()
    brand = settings.smtp_from_name or "IoTAPS"
    base_url = settings.public_base_url.rstrip("/")

    detail_html = ""
    if rows:
        cells = "".join(
            f"""<tr>
                  <td style="padding:6px 12px;color:#6b7280;font-size:13px;">{label}</td>
                  <td style="padding:6px 12px;color:#111827;font-size:13px;font-weight:600;">{value}</td>
                </tr>"""
            for label, value in rows
        )
        detail_html = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="margin:16px 0;border:1px solid #e5e7eb;border-radius:8px;border-collapse:separate;">
          {cells}
        </table>"""

    cta_html = ""
    if cta_label and cta_url:
        cta_html = f"""
        <div style="margin:24px 0;">
          <a href="{cta_url}" style="background:{accent};color:#ffffff;text-decoration:none;
             padding:11px 22px;border-radius:8px;font-size:14px;font-weight:600;display:inline-block;">
            {cta_label}
          </a>
        </div>"""

    note_html = (
        f'<p style="color:#6b7280;font-size:12px;line-height:1.6;margin-top:20px;">{note}</p>'
        if note
        else ""
    )

    return f"""<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:24px 0;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
          <tr>
            <td style="background:{accent};padding:18px 28px;">
              <span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:0.3px;">{brand}</span>
            </td>
          </tr>
          <tr>
            <td style="padding:28px;">
              <h1 style="margin:0 0 12px;color:#111827;font-size:20px;">{heading}</h1>
              <p style="color:#374151;font-size:14px;line-height:1.6;margin:0;">{intro}</p>
              {detail_html}
              {cta_html}
              {note_html}
            </td>
          </tr>
          <tr>
            <td style="padding:16px 28px;background:#f9fafb;border-top:1px solid #e5e7eb;">
              <p style="color:#9ca3af;font-size:11px;line-height:1.5;margin:0;">
                You're receiving this because you manage an account on {brand}.<br/>
                <a href="{base_url}" style="color:#9ca3af;">{base_url}</a>
              </p>
            </td>
          </tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


# ---------------------------------------------------------------------------
# Low-level SMTP send
# ---------------------------------------------------------------------------
def _send_sync(recipients: list[str], subject: str, html: str, text: str) -> None:
    """Blocking SMTP send (run in a thread). Raises on failure."""
    settings = get_settings()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((settings.smtp_from_name or "IoTAPS", settings.smtp_from_email))
    msg["To"] = ", ".join(recipients)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    host, port = settings.smtp_host, settings.smtp_port
    user, pwd = settings.smtp_username, settings.smtp_password

    if port == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, timeout=_SMTP_TIMEOUT, context=context) as server:
            if user:
                server.login(user, pwd)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=_SMTP_TIMEOUT) as server:
            if settings.smtp_use_tls:
                server.starttls(context=ssl.create_default_context())
            if user:
                server.login(user, pwd)
            server.send_message(msg)


async def send_email(
    to: str | Iterable[str],
    subject: str,
    html: str,
    text: str | None = None,
) -> bool:
    """Send one email to one or more recipients. Best-effort; never raises.

    Returns True on success, False when skipped (no SMTP / no recipients) or on
    a delivery error (logged, not raised) so callers stay on the happy path.
    """
    settings = get_settings()
    recipients = [to] if isinstance(to, str) else [r for r in to if r]
    recipients = [r for r in recipients if r]
    if not recipients:
        return False
    if not settings.email_enabled:
        logger.info("email_skipped_smtp_disabled", extra={"subject": subject})
        return False

    body_text = text or "This message requires an HTML-capable email client."
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_send_sync, recipients, subject, html, body_text),
            timeout=_SMTP_TIMEOUT + 5,
        )
        logger.info("email_sent", extra={"subject": subject, "count": len(recipients)})
        return True
    except Exception:  # noqa: BLE001 - email must never break the caller
        logger.warning("email_send_failed", exc_info=True, extra={"subject": subject})
        return False


# ---------------------------------------------------------------------------
# Recipient resolution
# ---------------------------------------------------------------------------
async def org_recipient_emails(session: AsyncSession, org_id) -> list[str]:
    """Emails to notify for an org: its Project_Center managers (fallback: any user)."""
    import uuid

    try:
        org_uuid = uuid.UUID(str(org_id))
    except (ValueError, TypeError):
        return []

    result = await session.execute(
        select(User.email).where(
            User.org_id == org_uuid, User.role == ROLE_PROJECT_CENTER
        )
    )
    emails = [r[0] for r in result.all() if r[0]]
    if emails:
        return emails
    # Fallback: notify any user in the org so an event is never silently dropped.
    result = await session.execute(select(User.email).where(User.org_id == org_uuid))
    return [r[0] for r in result.all() if r[0]]


# ---------------------------------------------------------------------------
# Event emails — device lifecycle
# ---------------------------------------------------------------------------
def _dash_url(path: str = "") -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}{path}"


async def notify_device_registered(session: AsyncSession, org_id, device) -> bool:
    """Email the org when a new device is provisioned."""
    recipients = await org_recipient_emails(session, org_id)
    if not recipients:
        return False
    label = (getattr(device, "label", None) or getattr(device, "device_uid", None) or "New device")
    html = _layout(
        heading="Device registered",
        intro=f"A new device <strong>{label}</strong> has been added to your account and is ready to connect.",
        rows=[
            ("Name", str(label)),
            ("Device UID", str(getattr(device, "device_uid", "") or "—")),
            ("Status", "Awaiting first connection"),
        ],
        note="Flash this token to your hardware to bring it online. Keep the device token secret.",
        cta_label="Open dashboard",
        cta_url=_dash_url("/devices"),
        accent="#059669",
    )
    text = f"Device registered: {label}. Open {_dash_url('/devices')} to manage it."
    return await send_email(recipients, f"Device registered: {label}", html, text)


async def notify_device_deleted(session: AsyncSession, org_id, *, label: str, device_uid: str | None) -> bool:
    """Email the org when a device is deleted (credentials revoked)."""
    recipients = await org_recipient_emails(session, org_id)
    if not recipients:
        return False
    name = label or device_uid or "A device"
    html = _layout(
        heading="Device removed",
        intro=f"The device <strong>{name}</strong> was deleted from your account. Its MQTT credentials have been revoked and it can no longer connect.",
        rows=[("Name", str(name)), ("Device UID", str(device_uid or "—"))],
        note="If this wasn't you, review your account activity and team access right away.",
        cta_label="Review devices",
        cta_url=_dash_url("/devices"),
        accent="#dc2626",
    )
    text = f"Device removed: {name}. Its credentials were revoked."
    return await send_email(recipients, f"Device removed: {name}", html, text)


# ---------------------------------------------------------------------------
# Event emails — billing
# ---------------------------------------------------------------------------
async def notify_payment_succeeded(
    session: AsyncSession, org_id, *, amount, currency: str = "INR", period_end=None
) -> bool:
    """Email the org on a successful payment / subscription activation."""
    recipients = await org_recipient_emails(session, org_id)
    if not recipients:
        return False
    rows = [("Amount", f"{currency} {amount}"), ("Plan", "Pro")]
    if period_end is not None:
        rows.append(("Active until", str(period_end)[:10]))
    html = _layout(
        heading="Payment received — you're on Pro",
        intro="Thanks! Your payment was successful and your Pro plan is active.",
        rows=rows,
        cta_label="View billing",
        cta_url=_dash_url("/billing"),
        accent="#059669",
    )
    text = f"Payment received: {currency} {amount}. Your Pro plan is active."
    return await send_email(recipients, "Payment received — Pro plan active", html, text)


async def notify_payment_failed(
    session: AsyncSession, org_id, *, amount=None, currency: str = "INR"
) -> bool:
    """Email the org when a payment fails (prior plan retained)."""
    recipients = await org_recipient_emails(session, org_id)
    if not recipients:
        return False
    rows = [("Amount", f"{currency} {amount}")] if amount is not None else None
    html = _layout(
        heading="Payment failed",
        intro="We couldn't process your subscription payment. Your previous plan stays unchanged — no access was lost — but please retry to continue on Pro.",
        rows=rows,
        note="Common causes: insufficient funds, expired card, or bank decline. Retrying usually resolves it.",
        cta_label="Retry payment",
        cta_url=_dash_url("/billing"),
        accent="#dc2626",
    )
    text = "Your subscription payment failed. Your previous plan is unchanged. Please retry."
    return await send_email(recipients, "Action needed: payment failed", html, text)


async def notify_subscription_expiring(
    session: AsyncSession, org_id, *, days_left: int, period_end=None, device_count=None
) -> bool:
    """Email the org when a subscription is close to lapsing ('low days')."""
    recipients = await org_recipient_emails(session, org_id)
    if not recipients:
        return False
    accent = "#dc2626" if days_left <= 1 else "#d97706"
    day_word = "day" if days_left == 1 else "days"
    rows = [("Time left", f"{days_left} {day_word}")]
    if period_end is not None:
        rows.append(("Expires on", str(period_end)[:10]))
    if device_count is not None:
        rows.append(("Devices covered", str(device_count)))
    html = _layout(
        heading=f"Your plan expires in {days_left} {day_word}",
        intro="Your Pro subscription is about to end. Renew now to avoid interruption to your devices and data collection.",
        rows=rows,
        note="When a plan lapses, paid features pause until you renew. Your data is retained.",
        cta_label="Renew now",
        cta_url=_dash_url("/billing"),
        accent=accent,
    )
    text = f"Your Pro plan expires in {days_left} {day_word}. Renew at {_dash_url('/billing')}."
    return await send_email(
        recipients, f"Your plan expires in {days_left} {day_word}", html, text
    )


async def notify_subscription_expired(session: AsyncSession, org_id, *, period_end=None) -> bool:
    """Email the org when a subscription has lapsed."""
    recipients = await org_recipient_emails(session, org_id)
    if not recipients:
        return False
    rows = [("Expired on", str(period_end)[:10])] if period_end is not None else None
    html = _layout(
        heading="Your Pro plan has expired",
        intro="Your subscription has lapsed and Pro features are now paused. Your data and devices are safe — renew anytime to restore full access.",
        rows=rows,
        cta_label="Reactivate Pro",
        cta_url=_dash_url("/billing"),
        accent="#dc2626",
    )
    text = "Your Pro plan has expired. Renew to restore full access."
    return await send_email(recipients, "Your Pro plan has expired", html, text)


async def notify_welcome(to: str, *, name: str | None = None) -> bool:
    """Welcome email for a new account."""
    greeting = f"Hi {name}," if name else "Welcome!"
    html = _layout(
        heading="Welcome to IoTAPS",
        intro=f"{greeting} Your account is ready. Register your first device, build a dashboard, and start streaming telemetry in minutes.",
        cta_label="Get started",
        cta_url=_dash_url("/devices"),
        accent="#4f46e5",
    )
    text = "Welcome to IoTAPS. Your account is ready — register your first device to begin."
    return await send_email(to, "Welcome to IoTAPS", html, text)


# ---------------------------------------------------------------------------
# Generic alert email (consumed by the Notification_Sender worker, Req 20.1)
# ---------------------------------------------------------------------------
async def alert_email_sender(email: str, subject: str, body: str) -> None:
    """Adapter matching the worker's EmailSender signature (email, subject, body).

    Wraps a rule-alert message in the branded layout. Raises on hard failure so
    the worker records the channel as failed (its dispatch isolates channels).
    """
    html = _layout(
        heading=subject or "Alert",
        intro=body or "An alert was triggered on one of your devices.",
        cta_label="View device",
        cta_url=_dash_url("/devices"),
        accent="#d97706",
    )
    ok = await send_email(email, subject or "IoTAPS alert", html, body)
    if not ok and get_settings().email_enabled:
        raise RuntimeError("alert email delivery failed")
