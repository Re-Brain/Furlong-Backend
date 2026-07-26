"""Transactional email for booking status changes, sent via Resend.

Email is a side effect of booking actions, never a precondition for them: every
public send_* function below swallows its own exceptions (via the @_safe
decorator) and only logs on failure, so a Resend outage or bad API key never
turns into a failed booking request.
"""
import functools
import logging
import os

import resend
from dotenv import load_dotenv

load_dotenv()

resend.api_key = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
# Dev-only: while on Resend's sandbox sender, delivery is restricted to the
# account's own verified address, so every email gets redirected here instead
# of its real recipient. Unset (or blank) this once a domain is verified.
EMAIL_OVERRIDE_TO = os.getenv("EMAIL_OVERRIDE_TO") or None

logger = logging.getLogger("email")

BRAND_NAME = "Furlong"

# Pulled from the app's own UI (cream/forest-green palette + pill status badges)
# so the email reads as the same product, not a generic notification.
COLORS = {
    "page_bg": "#F3ECDA",
    "card_bg": "#FFFFFF",
    "header_bg": "#1F3D2E",
    "row_bg": "#FAF6EB",
    "border": "#E6DCC6",
    "text": "#2B2B24",
    "muted": "#6B6153",
}

STATUS_STYLES = {
    "pending": {"bg": "#FBE8A6", "text": "#8A6A16", "label": "Pending"},
    "confirmed": {"bg": "#DCEEDD", "text": "#1F6B3A", "label": "Confirmed"},
    "declined": {"bg": "#F8D9D3", "text": "#B23A2E", "label": "Declined"},
    "cancelled": {"bg": "#EDE8DC", "text": "#6B6153", "label": "Cancelled"},
}

# App's horseshoe mark, recolored to white so it reads on the dark green header bar.
# Hosted on Cloudinary rather than embedded as a data URI: Gmail's image proxy
# strips inline `data:` image sources entirely, so a real HTTPS URL is required.
LOGO_URL = "https://res.cloudinary.com/drvur9wfo/image/upload/v1785058259/email-assets/furlong-horseshoe-logo.png"


def _safe(fn):
    """Never let a send raise. Returns True on success, False on failure (logged).

    The return value is ignored by the booking routes (email is fire-and-forget
    there), but the reminder job uses it to decide whether reminder_sent_at
    should be stamped, so a transient failure gets retried on the next run.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> bool:
        try:
            fn(*args, **kwargs)
            return True
        except Exception:
            logger.exception("Failed to send email via %s", fn.__name__)
            return False
    return wrapper


def _format_date(d) -> str:
    # Matches the dashboard's own "Fri, July 24, 2026" style (no zero-padded day).
    return f"{d.strftime('%a')}, {d.strftime('%B')} {d.day}, {d.year}"


def _format_time(hhmm: str) -> str:
    # "14:30" -> "2:30pm"; matches the dashboard's "12:00pm-4:00pm" style.
    h, m = (int(part) for part in hhmm.split(":"))
    period = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d}{period}"


def _detail_row(label: str, value: str, *, first: bool) -> str:
    border = "" if first else f"border-top:1px solid {COLORS['border']};"
    return (
        f'<tr>'
        f'<td style="padding:12px 18px;{border}font-family:Arial,Helvetica,sans-serif;'
        f'font-size:13px;color:{COLORS["muted"]};white-space:nowrap;">{label}</td>'
        f'<td style="padding:12px 18px;{border}font-family:Arial,Helvetica,sans-serif;'
        f'font-size:14px;color:{COLORS["text"]};font-weight:bold;width:100%;">{value}</td>'
        f'</tr>'
    )


def _render_email(
    status_key: str, heading: str, intro: str, contact_line: str, booking, note: str = None,
    reason: str = None,
) -> str:
    style = STATUS_STYLES[status_key]
    time_range = f"{_format_time(booking.start)}–{_format_time(booking.end)} ({booking.period})"

    row_list = [
        _detail_row("Horse", booking.horse_name, first=True),
        _detail_row("Farm", booking.farm_name, first=False),
        _detail_row("Date", _format_date(booking.date), first=False),
        _detail_row("Time", time_range, first=False),
    ]
    if reason:
        row_list.append(_detail_row("Reason", reason, first=False))
    rows = "".join(row_list)

    note_html = ""
    if note:
        note_html = f"""\
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;background-color:{style['bg']};border-radius:8px;">
              <tr><td style="padding:12px 16px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{style['text']};line-height:1.5;">{note}</td></tr>
            </table>"""

    return f"""\
<body style="margin:0;padding:0;background-color:{COLORS['page_bg']};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{COLORS['page_bg']};padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background-color:{COLORS['card_bg']};border-radius:12px;border:1px solid {COLORS['border']};overflow:hidden;">
        <tr>
          <td align="center" style="background-color:{COLORS['header_bg']};padding:24px 28px;">
            <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:0 auto;"><tr>
              <td style="vertical-align:middle;padding-right:14px;"><img src="{LOGO_URL}" width="48" height="48" alt="" style="display:block;border:0;" /></td>
              <td style="vertical-align:middle;"><span style="font-family:Georgia,'Times New Roman',serif;color:#FFFFFF;font-size:30px;font-weight:bold;letter-spacing:0.3px;">{BRAND_NAME}</span></td>
            </tr></table>
          </td>
        </tr>
        <tr>
          <td style="padding:28px;">
            <span style="display:inline-block;background-color:{style['bg']};color:{style['text']};font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:bold;text-transform:uppercase;letter-spacing:0.5px;padding:5px 14px;border-radius:999px;">{style['label']}</span>
            <h1 style="font-family:Georgia,'Times New Roman',serif;color:{COLORS['header_bg']};font-size:21px;margin:14px 0 8px;">{heading}</h1>
            <p style="font-family:Arial,Helvetica,sans-serif;color:{COLORS['text']};font-size:14px;line-height:1.6;margin:0 0 20px;">{intro}</p>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{COLORS['row_bg']};border:1px solid {COLORS['border']};border-radius:8px;overflow:hidden;">
              {rows}
            </table>
            <p style="font-family:Arial,Helvetica,sans-serif;color:{COLORS['muted']};font-size:13px;margin:20px 0 0;">{contact_line}</p>
{note_html}
          </td>
        </tr>
        <tr>
          <td style="background-color:{COLORS['row_bg']};border-top:1px solid {COLORS['border']};padding:14px 28px;">
            <p style="font-family:Arial,Helvetica,sans-serif;color:{COLORS['muted']};font-size:11px;margin:0;">This is an automated message from {BRAND_NAME}. Please don't reply directly to this email.</p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>"""


def _send_booking_email(
    to: str, subject: str, status_key: str, heading: str, intro: str, contact_line: str, booking,
    note: str = None, reason: str = None,
) -> None:
    if EMAIL_OVERRIDE_TO:
        subject = f"[to: {to}] {subject}"
        to = EMAIL_OVERRIDE_TO

    html = _render_email(status_key, heading, intro, contact_line, booking, note=note, reason=reason)
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
    })


@_safe
def send_new_booking_request(booking) -> None:
    """#1a Visitor creates a booking -> notify the farmer."""
    _send_booking_email(
        to=booking.farm.owner.email,
        subject=f"New booking request for {booking.horse_name}",
        status_key="pending",
        heading="New booking request",
        intro=f"{booking.visitor_name} has requested to visit {booking.horse_name}.",
        contact_line=f"Contact the visitor: {booking.visitor_name} ({booking.visitor_email})",
        booking=booking,
    )


@_safe
def send_new_booking_confirmation(booking) -> None:
    """#1b Visitor creates a booking -> also notify the visitor their request was submitted."""
    _send_booking_email(
        to=booking.visitor_email,
        subject=f"Your booking request has been sent: {booking.horse_name}",
        status_key="pending",
        heading="Your booking request has been sent",
        intro=f"Your request to visit {booking.horse_name} at {booking.farm_name} has been submitted.",
        contact_line=f"Farm: {booking.farm_name}",
        note="This isn't confirmed yet — please wait for the farmer to approve your request before you come to visit.",
        booking=booking,
    )


@_safe
def send_booking_cancelled_by_visitor(booking) -> None:
    """#2a Visitor cancels their booking -> notify the farmer."""
    _send_booking_email(
        to=booking.farm.owner.email,
        subject=f"Booking cancelled: {booking.horse_name}",
        status_key="cancelled",
        heading="Visitor cancelled their booking",
        intro=f"{booking.visitor_name} has cancelled their visit to {booking.horse_name}.",
        contact_line=f"Contact the visitor: {booking.visitor_name} ({booking.visitor_email})",
        booking=booking,
    )


@_safe
def send_booking_cancellation_receipt(booking) -> None:
    """#2b Visitor cancels their booking -> also confirm it to the visitor."""
    _send_booking_email(
        to=booking.visitor_email,
        subject=f"You cancelled your booking: {booking.horse_name}",
        status_key="cancelled",
        heading="You cancelled your booking",
        intro=f"You've cancelled your visit to {booking.horse_name} at {booking.farm_name}.",
        contact_line=f"Farm: {booking.farm_name}",
        booking=booking,
    )


@_safe
def send_booking_declined(booking) -> None:
    """#3a Farmer declines a pending request -> notify the visitor."""
    _send_booking_email(
        to=booking.visitor_email,
        subject=f"Your booking request was declined: {booking.horse_name}",
        status_key="declined",
        heading="Your booking request was declined",
        intro=f"{booking.farm_name} was unable to accept your visit request for {booking.horse_name}.",
        contact_line=f"Farm: {booking.farm_name}",
        reason=booking.reason,
        booking=booking,
    )


@_safe
def send_booking_declined_receipt(booking) -> None:
    """#3b Farmer declines a pending request -> also confirm it to the farmer."""
    _send_booking_email(
        to=booking.farm.owner.email,
        subject=f"You declined a booking request: {booking.horse_name}",
        status_key="declined",
        heading="You declined a booking request",
        intro=f"You declined {booking.visitor_name}'s request to visit {booking.horse_name}.",
        contact_line=f"Visitor: {booking.visitor_name} ({booking.visitor_email})",
        reason=booking.reason,
        booking=booking,
    )


@_safe
def send_booking_confirmed(booking) -> None:
    """#4a Farmer confirms a pending request -> notify the visitor."""
    _send_booking_email(
        to=booking.visitor_email,
        subject=f"Your booking is confirmed: {booking.horse_name}",
        status_key="confirmed",
        heading="Your booking is confirmed!",
        intro=f"{booking.farm_name} confirmed your visit to {booking.horse_name}.",
        contact_line=f"Farm: {booking.farm_name}",
        booking=booking,
    )


@_safe
def send_booking_confirmed_receipt(booking) -> None:
    """#4b Farmer confirms a pending request -> also confirm it to the farmer."""
    _send_booking_email(
        to=booking.farm.owner.email,
        subject=f"You confirmed a booking: {booking.horse_name}",
        status_key="confirmed",
        heading="You confirmed a booking",
        intro=f"You confirmed {booking.visitor_name}'s visit to {booking.horse_name}.",
        contact_line=f"Visitor: {booking.visitor_name} ({booking.visitor_email})",
        booking=booking,
    )


@_safe
def send_booking_cancelled_by_farmer(booking) -> None:
    """#5a Farmer cancels an already-confirmed visit -> notify the visitor."""
    _send_booking_email(
        to=booking.visitor_email,
        subject=f"Your booking was cancelled: {booking.horse_name}",
        status_key="cancelled",
        heading="Your booking was cancelled",
        intro=f"{booking.farm_name} had to cancel your confirmed visit to {booking.horse_name}.",
        contact_line=f"Farm: {booking.farm_name}",
        reason=booking.reason,
        booking=booking,
    )


@_safe
def send_booking_cancelled_by_farmer_receipt(booking) -> None:
    """#5b Farmer cancels an already-confirmed visit -> also confirm it to the farmer."""
    _send_booking_email(
        to=booking.farm.owner.email,
        subject=f"You cancelled a booking: {booking.horse_name}",
        status_key="cancelled",
        heading="You cancelled a booking",
        intro=f"You cancelled {booking.visitor_name}'s confirmed visit to {booking.horse_name}.",
        contact_line=f"Visitor: {booking.visitor_name} ({booking.visitor_email})",
        reason=booking.reason,
        booking=booking,
    )


@_safe
def send_pending_reminder(booking) -> None:
    """#6 Pending request nearing the visit date, still unanswered -> notify the farmer."""
    _send_booking_email(
        to=booking.farm.owner.email,
        subject=f"Reminder: booking request awaiting response for {booking.horse_name}",
        status_key="pending",
        heading="Booking request awaiting your response",
        intro=(
            f"A booking request from {booking.visitor_name} for {booking.horse_name} "
            "is still pending and the visit date is approaching."
        ),
        contact_line=f"Contact the visitor: {booking.visitor_name} ({booking.visitor_email})",
        booking=booking,
    )
