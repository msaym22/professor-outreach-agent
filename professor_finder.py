"""
professor_finder.py — Locate a professor's direct email address.

Strategy (in order):
  1. Scrape the faculty/lab page directly for mailto links or visible emails
  2. Hunter.io domain + name search
  3. Snov.io domain + name search
  4. Constructed guesses (firstname.lastname@domain, f.lastname@domain, etc.)
     verified via Hunter or trusted for .edu/.ac.* domains
"""
import json
import re
import requests
import time
import urllib3
from urllib.parse import urlparse
from config import AGGREGATOR_DOMAINS, _HUNTER_KEYS, _SNOV_CREDS
from llm_utils import cheap_complete
from email_utils import (
    verify_email_exists,
    email_domain_ok,
    get_active_hunter_key,
    rotate_hunter_key,
    get_active_snov_token,
    rotate_snov_key,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _domain_from_url(url):
    try:
        return urlparse(url).netloc.replace("www.", "").lower()
    except Exception:
        return ""


def _name_parts(full_name):
    parts = full_name.strip().split()
    return parts[0] if parts else "", parts[-1] if len(parts) > 1 else ""


def _email_guesses(first, last, domain):
    """Generate common academic email patterns."""
    f, l = first.lower(), last.lower()
    return [
        f"{f}.{l}@{domain}",
        f"{f[0]}.{l}@{domain}",
        f"{f}{l}@{domain}",
        f"{f}@{domain}",
        f"{l}@{domain}",
        f"{f}_{l}@{domain}",
    ]


def scrape_faculty_page(url):
    """
    Scrape a professor's faculty / lab page for their email and name.
    Tries the given URL and common sub-paths.
    """
    base = url.rstrip("/")
    for path in ("", "/contact", "/about", "/team", "/people"):
        try:
            resp = requests.get(
                base + path,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
                allow_redirects=True,
                verify=False,
            )
            if resp.status_code != 200:
                continue

            text_clean = re.sub(r"<[^>]+>", " ", resp.text)

            # Try to find email in the raw HTML (before tag stripping)
            raw_emails = re.findall(
                r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
                resp.text,
            )
            clean_emails = [
                e.strip(".,;:").lower()
                for e in raw_emails
                if email_domain_ok(e.strip(".,;:").lower())
            ]

            # Ask LLM to extract professor name and email from cleaned text
            prompt = (
                "Extract the professor's full name and email from this faculty/lab page text.\n"
                f"Text: {text_clean[:10000]}\n"
                'Return JSON: {"name": "Full Name", "email": "email@example.com"} '
                "(use null for missing fields)"
            )
            try:
                parsed = json.loads(cheap_complete(prompt))
                name  = parsed.get("name") or ""
                email = (parsed.get("email") or "").lower().strip()

                if email and email_domain_ok(email):
                    clean_emails.insert(0, email)

                return name or None, clean_emails[:5]
            except Exception:
                return None, clean_emails[:5]

        except Exception:
            continue

    return None, []


def hunter_domain_search(domain, first_name, last_name):
    """Use Hunter.io email-finder to get a professor's email."""
    for _ in range(len(_HUNTER_KEYS)):
        key = get_active_hunter_key()
        if not key:
            break
        try:
            res = requests.get(
                f"https://api.hunter.io/v2/email-finder"
                f"?domain={domain}&first_name={first_name}&last_name={last_name}&api_key={key}",
                timeout=10,
                verify=False,
            ).json()
            errors = res.get("errors") or []
            if errors:
                codes = [str(e.get("id", "")).lower() for e in errors]
                if any("auth" in c or "quota" in c or "limit" in c or "user" in c for c in codes):
                    if not rotate_hunter_key():
                        break
                    continue
                break
            if "data" in res and res["data"].get("email"):
                return res["data"]["email"]
            break
        except Exception:
            if not rotate_hunter_key():
                break
    return None


def snov_name_domain_search(domain, first_name, last_name):
    """Use Snov.io to find an email by name + domain."""
    for _ in range(len(_SNOV_CREDS)):
        token = get_active_snov_token()
        if not token:
            break
        headers = {"Authorization": f"Bearer {token}"}
        try:
            start_res = requests.post(
                "https://api.snov.io/v2/emails-by-domain-by-name/start",
                headers=headers,
                data={"firstName": first_name, "lastName": last_name, "domain": domain},
                timeout=10,
                verify=False,
            )
            if start_res.status_code in (401, 402, 429):
                if not rotate_snov_key():
                    break
                continue

            start_data = start_res.json()
            task_hash  = start_data.get("id") or start_data.get("task_hash")
            if not task_hash:
                break

            result_url = f"https://api.snov.io/v2/emails-by-domain-by-name/result/{task_hash}"
            for _ in range(5):
                time.sleep(2)
                poll = requests.get(result_url, headers=headers, timeout=10, verify=False)
                if poll.status_code == 200:
                    data = poll.json()
                    if isinstance(data, list) and data:
                        emails_obj = data[0].get("emails", [])
                        if emails_obj:
                            found = emails_obj[0].get("email")
                            if found:
                                return found
                    return None
                elif poll.status_code in (401, 402, 429):
                    rotate_snov_key()
                    break
        except Exception:
            rotate_snov_key()
    return None


def resolve_professor_domain(prof_name, lab_url):
    """
    Determine the professor's university domain from their lab URL or a SERP lookup.
    """
    # Primary: extract from the known URL
    domain = _domain_from_url(lab_url)
    if domain and domain not in AGGREGATOR_DOMAINS:
        return domain

    # Fallback: SERP search
    try:
        from discovery.serp import direct_serpapi_search
        results = direct_serpapi_search(f'"{prof_name}" professor university faculty email site:*.edu OR site:*.ac.*')
        if results:
            for item in results[:3]:
                link = item.get("link", "")
                d = _domain_from_url(link)
                if d and d not in AGGREGATOR_DOMAINS and ("edu" in d or ".ac." in d):
                    return d
    except Exception:
        pass
    return domain or None


def find_professor_contact(prof_name, lab_url, exclude_emails=None):
    """
    Master contact resolver for a professor.
    Returns (verified_name, verified_email) or (prof_name, None).
    """
    exclude = set(e.lower().strip() for e in (exclude_emails or []))

    # Step 1: Scrape the faculty/lab page
    scraped_name, scraped_emails = scrape_faculty_page(lab_url)
    verified_name = scraped_name or prof_name

    candidates = list(scraped_emails)

    # Step 2: Resolve university domain
    domain = resolve_professor_domain(prof_name, lab_url)

    # Step 3: Hunter + Snov name search
    if domain and prof_name and len(prof_name.split()) >= 2:
        first, last = _name_parts(prof_name)
        if first and last:
            hunter_email = hunter_domain_search(domain, first, last)
            if hunter_email and hunter_email not in candidates:
                candidates.insert(0, hunter_email)

            snov_email = snov_name_domain_search(domain, first, last)
            if snov_email and snov_email not in candidates:
                candidates.insert(1, snov_email)

    # Step 4: Email pattern guesses (verified for non-academic; trusted for .edu/.ac.*)
    if domain and prof_name and len(prof_name.split()) >= 2:
        first, last = _name_parts(prof_name)
        for guess in _email_guesses(first, last, domain):
            if guess not in candidates:
                candidates.append(guess)

    # Step 5: Verify and return first working email
    seen = set()
    for email in candidates:
        email_low = email.lower().strip()
        if email_low in seen or email_low in exclude:
            continue
        seen.add(email_low)
        if not email_domain_ok(email_low):
            continue
        if verify_email_exists(email_low):
            print(f"  ✉️  Found email: {email_low}")
            return verified_name, email_low

    print(f"  ⚠️  No verified email found for: {prof_name}")
    return verified_name, None
