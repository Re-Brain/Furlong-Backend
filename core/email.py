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

from core.stripe_client import FRONTEND_URL

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
    "approved": {"bg": "#DCEEDD", "text": "#1F6B3A", "label": "Approved"},
    "rejected": {"bg": "#F8D9D3", "text": "#B23A2E", "label": "Rejected"},
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


def _booking_rows(booking, reason: str = None) -> str:
    time_range = f"{_format_time(booking.start)}–{_format_time(booking.end)} ({booking.period})"
    row_list = [
        _detail_row("Horse", booking.horse_name, first=True),
        _detail_row("Farm", booking.farm_name, first=False),
        _detail_row("Date", _format_date(booking.date), first=False),
        _detail_row("Time", time_range, first=False),
    ]
    if reason:
        row_list.append(_detail_row("Reason", reason, first=False))
    return "".join(row_list)


def _horse_rows(horse, reason: str = None) -> str:
    row_list = [
        _detail_row("Horse", horse.name, first=True),
        _detail_row("Farm", horse.farm_name, first=False),
    ]
    if reason:
        row_list.append(_detail_row("Reason", reason, first=False))
    return "".join(row_list)


def _farm_rows(farm, reason: str = None) -> str:
    row_list = [
        _detail_row("Farm", farm.name, first=True),
    ]
    if reason:
        row_list.append(_detail_row("Reason", reason, first=False))
    return "".join(row_list)


def _render_email(status_key: str, heading: str, intro: str, contact_line: str, rows: str, note: str = None) -> str:
    style = STATUS_STYLES[status_key]

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

    html = _render_email(status_key, heading, intro, contact_line, _booking_rows(booking, reason=reason), note=note)
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
    })


def _send_horse_email(
    to: str, subject: str, status_key: str, heading: str, intro: str, contact_line: str, horse,
    note: str = None, reason: str = None,
) -> None:
    if EMAIL_OVERRIDE_TO:
        subject = f"[to: {to}] {subject}"
        to = EMAIL_OVERRIDE_TO

    html = _render_email(status_key, heading, intro, contact_line, _horse_rows(horse, reason=reason), note=note)
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
    })


def _send_farm_email(
    to: str, subject: str, status_key: str, heading: str, intro: str, contact_line: str, farm,
    note: str = None, reason: str = None,
) -> None:
    if EMAIL_OVERRIDE_TO:
        subject = f"[to: {to}] {subject}"
        to = EMAIL_OVERRIDE_TO

    html = _render_email(status_key, heading, intro, contact_line, _farm_rows(farm, reason=reason), note=note)
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
    })


def _render_verification_email(name: str, verify_url: str) -> str:
    # Different shape from every other email here — a call-to-action link,
    # not a status update — so it doesn't reuse _render_email's detail-row
    # table, just the same header/logo/brand chrome.
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
            <h1 style="font-family:Georgia,'Times New Roman',serif;color:{COLORS['header_bg']};font-size:21px;margin:0 0 8px;">Verify your email</h1>
            <p style="font-family:Arial,Helvetica,sans-serif;color:{COLORS['text']};font-size:14px;line-height:1.6;margin:0 0 20px;">Hi {name}, please confirm this is your email address to activate your {BRAND_NAME} account.</p>
            <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 20px;"><tr>
              <td style="background-color:{COLORS['header_bg']};border-radius:8px;">
                <a href="{verify_url}" style="display:inline-block;padding:12px 24px;font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:bold;color:#FFFFFF;text-decoration:none;">Verify Email</a>
              </td>
            </tr></table>
            <p style="font-family:Arial,Helvetica,sans-serif;color:{COLORS['muted']};font-size:12px;line-height:1.6;margin:0 0 8px;word-break:break-all;">Or paste this link into your browser: {verify_url}</p>
            <p style="font-family:Arial,Helvetica,sans-serif;color:{COLORS['muted']};font-size:12px;margin:0;">This link expires in 24 hours.</p>
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


def _send_verification_email(to: str, subject: str, name: str, verify_url: str) -> None:
    if EMAIL_OVERRIDE_TO:
        subject = f"[to: {to}] {subject}"
        to = EMAIL_OVERRIDE_TO

    html = _render_verification_email(name, verify_url)
    resend.Emails.send({
        "from": EMAIL_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
    })


@_safe
def send_verification_email(user, token: str) -> None:
    """Registration -> send the new account a link to confirm their email."""
    verify_url = f"{FRONTEND_URL}/verify-email?token={token}"
    _send_verification_email(
        to=user.email,
        subject="Verify your email address",
        name=user.name,
        verify_url=verify_url,
    )


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
def send_horse_submitted_for_review(horse, to: str) -> None:
    """#7a Farmer submits a draft horse for review -> notify an admin."""
    _send_horse_email(
        to=to,
        subject=f"New horse submitted for review: {horse.name}",
        status_key="pending",
        heading="New horse submitted for review",
        intro=f"{horse.farm_name} submitted {horse.name} for review.",
        contact_line=f"Farm: {horse.farm_name}",
        horse=horse,
    )


@_safe
def send_horse_submission_receipt(horse) -> None:
    """#7b Farmer submits a draft horse for review -> also confirm it to the farmer."""
    _send_horse_email(
        to=horse.farm.owner.email,
        subject=f"Your horse has been submitted for review: {horse.name}",
        status_key="pending",
        heading="Your horse has been submitted for review",
        intro=f"{horse.name} has been submitted and is now awaiting admin review.",
        contact_line=f"Farm: {horse.farm_name}",
        note="You'll be notified once a decision has been made. The horse's profile is locked until then.",
        horse=horse,
    )


@_safe
def send_horse_resubmitted_for_review(horse, to: str) -> None:
    """#8a Farmer resubmits a previously-rejected horse -> notify an admin."""
    _send_horse_email(
        to=to,
        subject=f"Horse resubmitted for review: {horse.name}",
        status_key="pending",
        heading="Horse resubmitted for review",
        intro=f"{horse.farm_name} made changes and resubmitted {horse.name} for review after a previous rejection.",
        contact_line=f"Farm: {horse.farm_name}",
        horse=horse,
    )


@_safe
def send_horse_resubmission_receipt(horse) -> None:
    """#8b Farmer resubmits a previously-rejected horse -> also confirm it to the farmer."""
    _send_horse_email(
        to=horse.farm.owner.email,
        subject=f"Your horse has been resubmitted for review: {horse.name}",
        status_key="pending",
        heading="Your horse has been resubmitted for review",
        intro=f"{horse.name} has been resubmitted and is now awaiting admin review.",
        contact_line=f"Farm: {horse.farm_name}",
        note="You'll be notified once a decision has been made. The horse's profile is locked until then.",
        horse=horse,
    )


@_safe
def send_horse_approved(horse) -> None:
    """#9a Admin approves a horse -> notify the farmer."""
    _send_horse_email(
        to=horse.farm.owner.email,
        subject=f"Your horse has been approved: {horse.name}",
        status_key="approved",
        heading="Your horse has been approved!",
        intro=f"{horse.name} has been approved and is now visible on {BRAND_NAME}.",
        contact_line=f"Farm: {horse.farm_name}",
        horse=horse,
    )


@_safe
def send_horse_approved_receipt(horse, admin_email: str) -> None:
    """#9b Admin approves a horse -> also confirm it to the admin who approved it."""
    _send_horse_email(
        to=admin_email,
        subject=f"You approved a horse: {horse.name}",
        status_key="approved",
        heading="You approved a horse",
        intro=f"You approved {horse.name} from {horse.farm_name}.",
        contact_line=f"Farm: {horse.farm_name}",
        horse=horse,
    )


@_safe
def send_horse_rejected(horse) -> None:
    """#10a Admin rejects a horse -> notify the farmer."""
    _send_horse_email(
        to=horse.farm.owner.email,
        subject=f"Your horse was rejected: {horse.name}",
        status_key="rejected",
        heading="Your horse was rejected",
        intro=f"{horse.name} was not approved.",
        contact_line=f"Farm: {horse.farm_name}",
        note="You can make changes and resubmit it for review at any time.",
        reason=horse.rejection_reason,
        horse=horse,
    )


@_safe
def send_horse_rejected_receipt(horse, admin_email: str) -> None:
    """#10b Admin rejects a horse -> also confirm it to the admin who rejected it."""
    _send_horse_email(
        to=admin_email,
        subject=f"You rejected a horse: {horse.name}",
        status_key="rejected",
        heading="You rejected a horse",
        intro=f"You rejected {horse.name} from {horse.farm_name}.",
        contact_line=f"Farm: {horse.farm_name}",
        reason=horse.rejection_reason,
        horse=horse,
    )


@_safe
def send_farm_submitted_for_review(farm, to: str) -> None:
    """#11a Farmer submits a draft farm for review -> notify an admin."""
    _send_farm_email(
        to=to,
        subject=f"New farm submitted for review: {farm.name}",
        status_key="pending",
        heading="New farm submitted for review",
        intro=f"{farm.name} was submitted for review.",
        contact_line=f"Farm: {farm.name}",
        farm=farm,
    )


@_safe
def send_farm_submission_receipt(farm) -> None:
    """#11b Farmer submits a draft farm for review -> also confirm it to the farmer."""
    _send_farm_email(
        to=farm.owner.email,
        subject=f"Your farm has been submitted for review: {farm.name}",
        status_key="pending",
        heading="Your farm has been submitted for review",
        intro=f"{farm.name} has been submitted and is now awaiting admin review.",
        contact_line=f"Farm: {farm.name}",
        note="You'll be notified once a decision has been made. Your farm's profile is locked until then.",
        farm=farm,
    )


@_safe
def send_farm_resubmitted_for_review(farm, to: str) -> None:
    """#12a Farmer resubmits a previously-rejected farm -> notify an admin."""
    _send_farm_email(
        to=to,
        subject=f"Farm resubmitted for review: {farm.name}",
        status_key="pending",
        heading="Farm resubmitted for review",
        intro=f"{farm.name} was resubmitted for review after a previous rejection.",
        contact_line=f"Farm: {farm.name}",
        farm=farm,
    )


@_safe
def send_farm_resubmission_receipt(farm) -> None:
    """#12b Farmer resubmits a previously-rejected farm -> also confirm it to the farmer."""
    _send_farm_email(
        to=farm.owner.email,
        subject=f"Your farm has been resubmitted for review: {farm.name}",
        status_key="pending",
        heading="Your farm has been resubmitted for review",
        intro=f"{farm.name} has been resubmitted and is now awaiting admin review.",
        contact_line=f"Farm: {farm.name}",
        note="You'll be notified once a decision has been made. Your farm's profile is locked until then.",
        farm=farm,
    )


@_safe
def send_farm_approved(farm) -> None:
    """#13a Admin approves a farm -> notify the farmer."""
    _send_farm_email(
        to=farm.owner.email,
        subject=f"Your farm has been approved: {farm.name}",
        status_key="approved",
        heading="Your farm has been approved!",
        intro=f"{farm.name} has been approved and is now visible on {BRAND_NAME}.",
        contact_line=f"Farm: {farm.name}",
        farm=farm,
    )


@_safe
def send_farm_approved_receipt(farm, admin_email: str) -> None:
    """#13b Admin approves a farm -> also confirm it to the admin who approved it."""
    _send_farm_email(
        to=admin_email,
        subject=f"You approved a farm: {farm.name}",
        status_key="approved",
        heading="You approved a farm",
        intro=f"You approved {farm.name}.",
        contact_line=f"Farm: {farm.name}",
        farm=farm,
    )


@_safe
def send_farm_rejected(farm) -> None:
    """#14a Admin rejects a farm -> notify the farmer."""
    _send_farm_email(
        to=farm.owner.email,
        subject=f"Your farm was rejected: {farm.name}",
        status_key="rejected",
        heading="Your farm was rejected",
        intro=f"{farm.name} was not approved.",
        contact_line=f"Farm: {farm.name}",
        note="You can make changes and resubmit it for review at any time.",
        reason=farm.rejection_reason,
        farm=farm,
    )


@_safe
def send_farm_rejected_receipt(farm, admin_email: str) -> None:
    """#14b Admin rejects a farm -> also confirm it to the admin who rejected it."""
    _send_farm_email(
        to=admin_email,
        subject=f"You rejected a farm: {farm.name}",
        status_key="rejected",
        heading="You rejected a farm",
        intro=f"You rejected {farm.name}.",
        contact_line=f"Farm: {farm.name}",
        reason=farm.rejection_reason,
        farm=farm,
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
