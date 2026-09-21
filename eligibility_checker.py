"""
eligibility_checker.py — Professor-specific eligibility and deduplication.

Checks:
  1. Is the institution blocked (MIT, Stanford, etc.)?
  2. Is the research overlap score above threshold?
  3. Is this a duplicate professor name?
"""
import re
import json
import requests
import urllib3
from rapidfuzz import fuzz
from config import BLOCKED_INSTITUTION_DOMAINS, BLOCKED_INSTITUTION_KEYWORDS
from llm_utils import cheap_complete

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Minimum overlap score (0-100) to proceed with outreach
MIN_OVERLAP_SCORE = 45

_eligibility_cache = {}


def is_blocked_institution(university: str, domain: str) -> bool:
    """
    Return True if the institution is in the blocked list.
    Checks both domain and institution name keywords.
    """
    if domain:
        domain_clean = domain.lower().replace("www.", "").strip()
        if domain_clean in BLOCKED_INSTITUTION_DOMAINS:
            return True

    if university:
        uni_lower = university.lower()
        for kw in BLOCKED_INSTITUTION_KEYWORDS:
            if kw in uni_lower:
                return True
    return False


def has_sufficient_overlap(overlap_score: int) -> bool:
    """Return True if the overlap score meets the minimum threshold."""
    return int(overlap_score or 0) >= MIN_OVERLAP_SCORE


def is_duplicate_professor(prof_name: str, seen_names: set) -> bool:
    """Fuzzy match to avoid emailing the same professor twice."""
    if not prof_name:
        return False
    for seen in seen_names:
        if fuzz.token_sort_ratio(prof_name.lower(), seen.lower()) > 88:
            return True
    return False


def check_professor_eligibility(prof_name, university, university_domain, overlap_score, seen_names):
    """
    Master eligibility gate. Returns a dict:
      {"is_eligible": bool, "reason": str}
    """
    # 1. Blocked institution check
    if is_blocked_institution(university, university_domain):
        return {"is_eligible": False, "reason": f"Blocked institution: {university}"}

    # 2. Overlap score check
    if not has_sufficient_overlap(overlap_score):
        return {
            "is_eligible": False,
            "reason": f"Low research overlap: {overlap_score}/100 (min {MIN_OVERLAP_SCORE})"
        }

    # 3. Duplicate check
    if is_duplicate_professor(prof_name, seen_names):
        return {"is_eligible": False, "reason": f"Duplicate: {prof_name}"}

    return {"is_eligible": True, "reason": "Passed all checks"}
