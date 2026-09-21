"""
agent.py — Professor Research Outreach Agent

Pipeline:
  1. SERP discovery → find professors matching Saim's research profile
  2. Eligibility check → block elite institutions, low-overlap
  3. Contact resolver → find professor's direct email
  4. Email drafting → professional, personalised cold email (paid RA ask)
  5. Send via Gmail (CV attached)
  6. Log to Google Sheet
"""

import json
import os
import sys
import traceback
import time
from pathlib import Path
from datetime import datetime

import httpx
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── SSL bypass for corporate proxies ─────────────────────────────────────────
if not getattr(httpx.Client.__init__, "_ssl_bypass_patched", False):
    _orig_httpx = httpx.Client.__init__
    def _patch_httpx(self, *a, **kw): kw["verify"] = False; _orig_httpx(self, *a, **kw)
    _patch_httpx._ssl_bypass_patched = True
    httpx.Client.__init__ = _patch_httpx

if not getattr(httpx.AsyncClient.__init__, "_ssl_bypass_patched", False):
    _orig_async = httpx.AsyncClient.__init__
    def _patch_async(self, *a, **kw): kw["verify"] = False; _orig_async(self, *a, **kw)
    _patch_async._ssl_bypass_patched = True
    httpx.AsyncClient.__init__ = _patch_async

if not getattr(requests.Session.request, "_ssl_bypass_patched", False):
    _orig_req = requests.Session.request
    def _patch_req(self, m, u, *a, **kw): kw["verify"] = False; return _orig_req(self, m, u, *a, **kw)
    _patch_req._ssl_bypass_patched = True
    requests.Session.request = _patch_req
# ─────────────────────────────────────────────────────────────────────────────

from dotenv import load_dotenv
load_dotenv()

from config import (
    EMAIL_TEMPLATE_HINTS,
    USER_BIO,
    SENDER_EMAIL,
    WEEKLY_REPORT_TO,
    MAX_EMAILS_PER_RUN,
)
from state import get_all_seen_urls, add_seen_url
from email_utils import gmail_send
from sheet_utils import append_sheet_row
from professor_finder import find_professor_contact
from eligibility_checker import check_professor_eligibility, is_duplicate_professor
from llm_utils import premium_complete
from discovery.serp import process_query_list
from logger import stats, send_failure_alert, send_success_summary, log

seen_prof_names: set = set()
seen_urls: list      = []


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL DRAFTING
# ─────────────────────────────────────────────────────────────────────────────

def draft_professor_email(
    prof_name: str,
    university: str,
    research_area: str,
    research_summary: str,
    overlap_score: int,
    open_to_collaboration: bool,
    lab_url: str,
) -> tuple[str, str]:
    """
    Draft a professional, personalised cold email to a professor.

    Primary ask: paid Research Assistantship (RA).
    Fallback mention: open to unpaid remote collaboration.
    Max 250 words. No hollow flattery. CV attached separately.
    """
    hint = EMAIL_TEMPLATE_HINTS.get(research_area, EMAIL_TEMPLATE_HINTS.get("University Lab", ""))

    open_signal = (
        "Their lab page indicates they are open to new students or collaborators — "
        "mention this directly to show you did your research."
        if open_to_collaboration else ""
    )

    prompt = (
        f"You are drafting a cold email on behalf of Muhammad Saim to Professor {prof_name} "
        f"at {university}.\n\n"
        f"Candidate profile:\n{USER_BIO}\n\n"
        f"Professor's research area: {research_area}\n"
        f"Research summary: {research_summary}\n"
        f"Lab/Faculty URL: {lab_url}\n"
        f"Research overlap score: {overlap_score}/100\n\n"
        f"Strategy hint: {hint}\n"
        f"{open_signal}\n\n"
        "Rules for the email:\n"
        "- Professional academic tone. No hollow compliments.\n"
        "- Open with a specific reference to the professor's research (use the research summary).\n"
        "- Introduce Saim as a 19-year-old CS undergraduate from Pakistan.\n"
        "- Highlight the 1-2 most relevant projects from his profile that match this professor's work.\n"
        "- Primary ask: express interest in a PAID Research Assistantship (RA) position, "
        "  remote or in-person.\n"
        "- Secondary: if RA is not available, mention openness to unpaid remote collaboration.\n"
        "- Mention that his CV is attached.\n"
        "- End with a low-friction call to action: "
        "  'Would you be open to a brief email exchange or a short call?'\n"
        "- Maximum 250 words. No placeholders like [Your Name]. Sign off as Muhammad Saim.\n\n"
        'Return JSON: {"subject": "...", "body": "..."}'
    )

    try:
        res = json.loads(premium_complete(prompt))
        subject = res.get("subject", "")
        body    = res.get("body", "")
        if subject and body:
            return subject, body
        log.warning(f"LLM returned empty email for {prof_name}")
        return "", ""
    except Exception as e:
        log.error(f"Failed to draft email for {prof_name}: {e}")
        return "", ""


# ─────────────────────────────────────────────────────────────────────────────
# PROFESSOR CALLBACK — called once per qualifying professor found
# ─────────────────────────────────────────────────────────────────────────────

def process_professor_callback(
    research_area: str,
    prof_name: str,
    university: str,
    university_domain: str,
    lab_url: str,
    research_summary: str,
    overlap_score: int,
    open_to_collaboration: bool,
):
    global seen_urls, seen_prof_names

    if not lab_url or lab_url in seen_urls:
        return
    add_seen_url(lab_url)
    seen_urls.append(lab_url)

    stats.discovered += 1

    # ── Eligibility gate ──────────────────────────────────────────────────────
    eligibility = check_professor_eligibility(
        prof_name, university, university_domain, overlap_score, seen_prof_names
    )
    if not eligibility.get("is_eligible"):
        reason = eligibility.get("reason", "unknown")
        log.info(f"Skipped ({reason}): {prof_name} @ {university}")

        if "Blocked" in reason:
            stats.skipped_blocked += 1
        elif "overlap" in reason.lower():
            stats.skipped_inel += 1
        else:
            stats.skipped_dupe += 1
        return

    seen_prof_names.add(prof_name)
    log.info(f"\n[overlap:{overlap_score}] Found: {prof_name} @ {university} ({research_area})")
    log.info(f"  Lab: {lab_url}")

    # ── Contact resolution ────────────────────────────────────────────────────
    verified_name, contact_email = find_professor_contact(prof_name, lab_url)
    if not contact_email:
        log.info(f"  No contact found for {prof_name}")
        append_sheet_row(
            research_area, verified_name or prof_name, university, lab_url,
            "", "no contact", overlap_score, research_summary,
        )
        stats.no_contact += 1
        return

    # ── Draft email ───────────────────────────────────────────────────────────
    subject, body = draft_professor_email(
        prof_name=verified_name or prof_name,
        university=university,
        research_area=research_area,
        research_summary=research_summary,
        overlap_score=overlap_score,
        open_to_collaboration=open_to_collaboration,
        lab_url=lab_url,
    )
    if not subject or not body:
        log.warning(f"  Email drafting failed for {prof_name} — skipping")
        return

    # ── Send ──────────────────────────────────────────────────────────────────
    sent, thread_id = gmail_send(
        to_email=contact_email,
        subject=subject,
        body=body,
        attach_cv=True,
        prof_name=verified_name or prof_name,
    )
    status = "sent" if sent else "error sending"

    if sent:
        stats.sent += 1
        log.info(f"  ✅ Email sent to {contact_email}")
    else:
        stats.failed_send += 1
        log.warning(f"  ❌ Failed to send to {contact_email}")

    # ── Log to sheet ──────────────────────────────────────────────────────────
    append_sheet_row(
        research_area=research_area,
        prof_name=verified_name or prof_name,
        university=university,
        lab_url=lab_url,
        email=contact_email,
        status=status,
        overlap_score=overlap_score,
        research_summary=research_summary,
        thread_id=thread_id or "",
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    global seen_urls, seen_prof_names

    log.info("=" * 60)
    log.info("  Professor Outreach Agent — starting run")
    log.info(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    # Load previously seen URLs from DB
    seen_urls = get_all_seen_urls()

    try:
        # ── Discovery via SERP ────────────────────────────────────────────────
        log.info("\n🔍 Starting professor discovery via SerpAPI...")
        process_query_list(
            seen_urls=seen_urls,
            seen_prof_names=seen_prof_names,
            callback=process_professor_callback,
        )

    except KeyboardInterrupt:
        log.info("\nInterrupted by user.")
    except Exception as e:
        tb = traceback.format_exc()
        log.critical(f"PIPELINE CRASHED:\n{tb}")
        send_failure_alert(tb, gmail_send_fn=gmail_send, sender_email=SENDER_EMAIL)

    finally:
        # ── Send summary ──────────────────────────────────────────────────────
        send_success_summary(gmail_send_fn=gmail_send, sender_email=SENDER_EMAIL)
        log.info("\nRun complete.")


if __name__ == "__main__":
    main()
