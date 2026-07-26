"""Daily job: remind farmers about pending booking requests nearing their visit date.

Run on a schedule (cron / Windows Task Scheduler / etc.), e.g. once a day:
    python -m scripts.send_booking_reminders

Each booking is reminded at most once: reminder_sent_at is only stamped after a
successful send, so a bad run (e.g. Resend outage) is simply retried the next
time this job runs, and a booking that already got its reminder is never
picked up again.
"""
import logging
import os
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv

from core import email
from database import SessionLocal
import models.models as models

load_dotenv()

logger = logging.getLogger("send_booking_reminders")

# How close to the visit date a still-pending request has to be before the
# farmer gets nudged. Kept separate from a farm's own min_lead_days (that
# governs how far ahead visitors must book, not when the farmer gets reminded).
REMINDER_LEAD_DAYS = int(os.getenv("BOOKING_REMINDER_LEAD_DAYS", "2"))


def run() -> int:
    """Send a reminder for every still-pending booking whose visit date is
    within REMINDER_LEAD_DAYS and hasn't been reminded yet. Returns the count sent."""
    db = SessionLocal()
    sent = 0
    try:
        today = date.today()
        threshold = today + timedelta(days=REMINDER_LEAD_DAYS)
        due = (
            db.query(models.Booking)
            .filter(
                models.Booking.status == "pending",
                models.Booking.date >= today,
                models.Booking.date <= threshold,
                models.Booking.reminder_sent_at.is_(None),
            )
            .all()
        )
        for booking in due:
            if email.send_pending_reminder(booking):
                booking.reminder_sent_at = datetime.now(timezone.utc)
                sent += 1
        db.commit()
    finally:
        db.close()
    return sent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = run()
    logger.info("Sent %d pending-booking reminder(s)", count)
