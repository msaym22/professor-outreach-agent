import time
import requests
import urllib3
import shutil
from tenacity import retry, stop_after_attempt, wait_exponential
from config import _HUNTER_KEYS, _SNOV_CREDS, MAX_EMAILS_PER_RUN, AGGREGATOR_DOMAINS, CV_PATH, CV_SOURCE
from state import mark_email_sent, has_emailed
from sheet_utils import safe_execute

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_hunter_key_index   = 0
_snov_index         = 0
_snov_token_cache   = {}
_emails_sent_this_run = 0


def get_active_hunter_key():
    return _HUNTER_KEYS[_hunter_key_index] if _HUNTER_KEYS else None


def rotate_hunter_key():
    global _hunter_key_index
    if len(_HUNTER_KEYS) > 1:
        next_index = (_hunter_key_index + 1) % len(_HUNTER_KEYS)
        if next_index != _hunter_key_index:
            _hunter_key_index = next_index
            print(f"Hunter quota hit — rotated to key #{_hunter_key_index + 1}")
            return True
    return False


def get_active_snov_token():
    global _snov_token_cache
    if not _SNOV_CREDS:
        return None
    idx    = _snov_index
    cached = _snov_token_cache.get(idx)
    if cached and cached[1] > time.time() + 60:
        return cached[0]

    client_id, client_secret = _SNOV_CREDS[idx]
    try:
        res = requests.post(
            "https://api.snov.io/v1/oauth/access_token",
            data={
                "grant_type":    "client_credentials",
                "client_id":     client_id,
                "client_secret": client_secret,
            },
            timeout=10,
            verify=False,
        ).json()
        if "access_token" in res:
            token = res["access_token"]
            _snov_token_cache[idx] = (token, time.time() + res.get("expires_in", 3600))
            return token
    except Exception as e:
        print(f"Snov.io Auth error on key #{idx + 1}: {e}")
    return None


def rotate_snov_key():
    global _snov_index
    if len(_SNOV_CREDS) > 1:
        next_index = (_snov_index + 1) % len(_SNOV_CREDS)
        if next_index != _snov_index:
            _snov_index = next_index
            print(f"Snov.io quota hit — rotated to account #{_snov_index + 1}")
            return True
    return False


def email_domain_ok(email):
    if not email or "@" not in email:
        return False
    domain = email.split("@")[-1].lower().replace("www.", "")
    # For professors, we also accept .edu, .ac.* domains — never block these
    return domain not in AGGREGATOR_DOMAINS


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
def _hunter_verify(email):
    global _hunter_key_index
    for _ in range(len(_HUNTER_KEYS)):
        key = get_active_hunter_key()
        if not key:
            break
        try:
            res = requests.get(
                f"https://api.hunter.io/v2/email-verifier?email={email}&api_key={key}",
                timeout=10,
                verify=False,
            ).json()

            errors = res.get("errors") or []
            if errors:
                codes = [str(e.get("id", "")).lower() for e in errors]
                if any("auth" in c or "quota" in c or "limit" in c or "user" in c for c in codes):
                    if not rotate_hunter_key():
                        return None
                    continue
                return False

            data    = res.get("data") or {}
            verdict = (data.get("status") or data.get("result") or "").lower()
            return verdict in {"valid", "accept_all", "webmail"}
        except Exception:
            if not rotate_hunter_key():
                return None
    return None


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
def _snov_verify(email):
    global _snov_index
    for _ in range(len(_SNOV_CREDS)):
        token = get_active_snov_token()
        if not token:
            break
        headers = {"Authorization": f"Bearer {token}"}
        try:
            start_res = requests.post(
                "https://api.snov.io/v2/email-verification/verify-emails",
                headers=headers,
                data={"emails[]": [email]},
                timeout=10,
                verify=False,
            )
            if start_res.status_code in (401, 402, 429):
                if not rotate_snov_key():
                    break
                continue

            task_hash = start_res.json().get("task_hash")
            if not task_hash:
                return None

            result_url = f"https://api.snov.io/v2/email-verification/result/{task_hash}"
            for _ in range(5):
                time.sleep(2)
                poll = requests.get(result_url, headers=headers, timeout=10, verify=False)
                if poll.status_code == 200:
                    data = poll.json()
                    if isinstance(data, list) and data:
                        status = data[0].get("status", "")
                        return status in ("valid", "unverifiable", "accept_all")
                elif poll.status_code in (401, 402, 429):
                    rotate_snov_key()
                    break
        except Exception:
            rotate_snov_key()
    return None


def verify_email_exists(email):
    """
    Verify an email is real. For .edu / .ac.* addresses we trust them by default
    (universities often block external verification services).
    """
    if not email or "@" not in email:
        return False
    domain = email.split("@")[-1].lower().replace("www.", "")
    if domain in AGGREGATOR_DOMAINS:
        return False

    # Trust academic domains without verification — they usually block Hunter/Snov
    if domain.endswith(".edu") or ".ac." in domain or domain.endswith(".edu.pk"):
        return True
    # Skip personal email services
    if domain in {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com"}:
        return False

    if _HUNTER_KEYS:
        result = _hunter_verify(email)
        if result is not None:
            return result

    if _SNOV_CREDS:
        result = _snov_verify(email)
        if result is not None:
            return result

    return True


def ensure_cv_available():
    CV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CV_PATH.exists():
        return CV_PATH
    if CV_SOURCE and CV_SOURCE.exists():
        shutil.copy2(CV_SOURCE, CV_PATH)
        return CV_PATH
    return None


def can_send_more_emails():
    return _emails_sent_this_run < MAX_EMAILS_PER_RUN


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def gmail_send(to_email, subject, body, attach_cv=True, prof_name="", thread_id=None):
    global _emails_sent_this_run

    if has_emailed(to_email) and "Weekly Outreach Report" not in subject:
        print(f"  ⏭️  Skipping {to_email}: Already emailed previously.")
        return False, None

    if not can_send_more_emails() and "Weekly Outreach Report" not in subject:
        print(f"  ⚠️  Email cap reached ({MAX_EMAILS_PER_RUN}). Skipping send.")
        return False, None

    args = {"to": to_email, "subject": subject, "body": body}
    if attach_cv:
        cv = ensure_cv_available()
        if cv:
            args["attachment"] = str(cv)
        else:
            print("  🚫  BLOCKED: CV file missing, will not send half-complete email.")
            return False, None

    if thread_id:
        args["thread_id"] = thread_id

    print(f"  📤 Sending → {to_email} | Subject: {subject[:60]}")
    res = safe_execute("GMAIL_SEND_EMAIL", args)

    sent_thread_id = None
    if res and isinstance(res, dict):
        sent_thread_id = res.get("threadId") or res.get("thread_id") or res.get("id")

    if res:
        print(f"  ✅ SENT successfully → {to_email}")
        if "Weekly Outreach Report" not in subject:
            _emails_sent_this_run += 1
            mark_email_sent(to_email, prof_name)
        return True, sent_thread_id
    else:
        print(f"  ❌ FAILED to send → {to_email}")
        return False, None
