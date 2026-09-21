"""
logger.py — Structured logging, pipeline stats, and email alerts.
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR  = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

_run_ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
_log_file = LOG_DIR / f"run_{_run_ts}.log"

_formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(module)-22s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file_handler    = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setFormatter(_formatter)

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_formatter)

log = logging.getLogger("prof_outreach")
log.setLevel(logging.DEBUG)
log.addHandler(_file_handler)
log.addHandler(_console_handler)


def get_log_path():
    return str(_log_file)


class PipelineStats:
    def __init__(self):
        self.discovered      = 0
        self.sent            = 0
        self.failed_send     = 0
        self.skipped_dupe    = 0
        self.skipped_blocked = 0  # blocked institution
        self.skipped_inel    = 0  # no research overlap
        self.no_contact      = 0

    def summary_lines(self):
        return [
            f"📊 Professor Outreach Run — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "─" * 55,
            f"  🔍 Professors discovered        : {self.discovered}",
            f"  📧 Emails sent                  : {self.sent}",
            f"  ❌ Failed sends                 : {self.failed_send}",
            f"  👤 No contact found             : {self.no_contact}",
            f"  ⏭️  Skipped (duplicate)         : {self.skipped_dupe}",
            f"  🏛️  Skipped (blocked institution): {self.skipped_blocked}",
            f"  🚫 Skipped (no overlap)         : {self.skipped_inel}",
            "─" * 55,
        ]

    def log_summary(self):
        for line in self.summary_lines():
            log.info(line)


stats = PipelineStats()


def send_failure_alert(error_msg: str, gmail_send_fn=None, sender_email: str = ""):
    log.critical(f"PIPELINE CRASHED: {error_msg}")
    if not gmail_send_fn or not sender_email:
        return
    subject = f"🚨 Professor Outreach CRASHED — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    body = (
        f"The professor outreach pipeline crashed at {datetime.now().strftime('%Y-%m-%d %H:%M')}.\n\n"
        f"Error:\n{error_msg}\n\nLog file: {_log_file}"
    )
    try:
        gmail_send_fn(sender_email, subject, body, attach_cv=False)
    except Exception as e:
        log.error(f"Could not send failure alert: {e}")


def send_success_summary(gmail_send_fn=None, sender_email: str = ""):
    stats.log_summary()
    if not gmail_send_fn or not sender_email:
        return
    subject = (
        f"✅ Professor Outreach Done — {stats.sent} sent, {stats.discovered} found "
        f"— {datetime.now().strftime('%Y-%m-%d')}"
    )
    body = "\n".join(stats.summary_lines()) + f"\n\nFull log: {_log_file}"
    try:
        gmail_send_fn(sender_email, subject, body, attach_cv=False)
    except Exception as e:
        log.error(f"Could not send success summary: {e}")
