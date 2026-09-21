"""
discovery/serp.py — SerpAPI-powered professor discovery.

Runs all QUERY_GROUPS through Google Search, applies 2-pass classification,
and triggers a callback for each valid professor found.

No geography priority scoring — all universities treated on equal merit.
"""
import json
import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import _SERP_KEYS, QUERY_GROUPS
from llm_utils import pass_1_binary_filter, pass_2_professor_classify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_serp_key_index = 0


def get_active_serp_key():
    return _SERP_KEYS[_serp_key_index] if _SERP_KEYS else None


def rotate_serp_key():
    global _serp_key_index
    if len(_SERP_KEYS) > 1:
        _serp_key_index = (_serp_key_index + 1) % len(_SERP_KEYS)
        print(f"SerpAPI quota hit — rotated to key #{_serp_key_index + 1}")


def direct_serpapi_search(query):
    """Run a single SerpAPI query and return organic results."""
    for attempt in range(2):
        active_key = get_active_serp_key()
        if not active_key:
            print("No SerpAPI keys available!")
            return {}
        try:
            resp = requests.get(
                "https://serpapi.com/search",
                params={"q": query, "api_key": active_key},
                timeout=20,
            )
            data = resp.json()
            if "error" in data:
                err_str = str(data["error"]).lower()
                print(f"SerpAPI Error: {err_str}")
                if any(kw in err_str for kw in ("quota", "rate", "limit", "run out", "searches", "exceeded")):
                    rotate_serp_key()
                    if attempt == 0:
                        continue
                return {}
            return data.get("organic_results", [])
        except Exception as e:
            print(f"SerpAPI Request failed: {e}")
            return {}
    return {}


def process_query_list(seen_urls, seen_prof_names, callback):
    """
    Execute all professor discovery queries in parallel.
    For each result that passes the 2-pass filter, fire the callback.

    callback signature:
        callback(
            research_area, prof_name, university, university_domain,
            lab_url, research_summary, overlap_score, open_to_collaboration
        )
    """
    from state import can_run_serp_today, mark_serp_ran

    if not can_run_serp_today():
        print("  ⏭️ SerpAPI already ran today. Skipping to save quota.")
        return

    mark_serp_ran()

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(direct_serpapi_search, q): (track, q)
            for track, q in QUERY_GROUPS
        }
        for future in as_completed(futures):
            track_type, q = futures[future]
            results = future.result()
            if not results:
                continue

            for item in results[:10]:
                link    = item.get("link") or ""
                title   = item.get("title") or ""
                snippet = item.get("snippet") or ""

                if not link.startswith("http") or link in seen_urls:
                    continue

                # Pass 1 — fast binary: is this a professor / lab page?
                if not pass_1_binary_filter(title, snippet):
                    continue

                # Fetch page text for deeper analysis
                try:
                    resp      = requests.get(link, timeout=10, headers={"User-Agent": "Mozilla/5.0"}, verify=False)
                    page_text = resp.text[:5000] if resp.status_code == 200 else snippet
                except Exception:
                    page_text = snippet

                # Pass 2 — deep classification
                deep = pass_2_professor_classify(link, page_text)

                if not deep:
                    continue

                # If the LLM flags this as a blocked elite institution, skip
                if deep.get("is_blocked"):
                    print(f"  🏛️  Blocked institution detected: {deep.get('university', link)}")
                    continue

                # Require a meaningful professor name
                prof_name = deep.get("professor_name") or title
                if not prof_name or len(prof_name.strip()) < 4:
                    continue

                # Require non-trivial overlap
                overlap = int(deep.get("overlap_score", 0))
                if overlap < 30:  # pre-filter before the eligibility checker's 45 threshold
                    continue

                callback(
                    research_area        = deep.get("research_area") or track_type,
                    prof_name            = prof_name.strip(),
                    university           = deep.get("university") or "",
                    university_domain    = deep.get("university_domain") or "",
                    lab_url              = link,
                    research_summary     = deep.get("research_summary") or snippet[:200],
                    overlap_score        = overlap,
                    open_to_collaboration= bool(deep.get("open_to_collaboration", False)),
                )
