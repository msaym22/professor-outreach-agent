import re
import json
from openai import OpenAI
from config import OPENROUTER_API_KEY, FREE_MODELS, DRAFT_MODEL, USER_BIO, TARGET_RESEARCH_AREAS
from tenacity import retry, stop_after_attempt, wait_exponential

llm_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "HTTP-Referer": "https://github.com/msaym22/professor-outreach",
        "X-Title": "Professor Outreach Agent",
    },
)


def extract_json_from_text(content):
    """Pull the first JSON object/array from model output."""
    if not content:
        return "{}"
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1)
    for pattern in (r"\{.*\}", r"\[.*\]"):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(0)
    return text


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def cheap_complete(prompt):
    """Call free-tier models for bulk classification."""
    for model in FREE_MODELS:
        try:
            res = llm_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            content = res.choices[0].message.content or ""
            result  = extract_json_from_text(content)
            if result and result.strip() not in ("{}", "[]", ""):
                return result
            print(f"Model {model} returned empty — trying next free model")
        except Exception as e:
            print(f"Free model {model} failed ({e}) — trying next")
            continue

    print(f"All free models failed — falling back to paid {DRAFT_MODEL}")
    try:
        res = llm_client.chat.completions.create(
            model=DRAFT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return res.choices[0].message.content or "{}"
    except Exception as e2:
        print(f"Paid model also failed: {e2}")
        return "{}"


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
def premium_complete(prompt):
    """Call paid model for high-quality email drafting."""
    res = llm_client.chat.completions.create(
        model=DRAFT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return extract_json_from_text(res.choices[0].message.content or "{}")


def pass_1_binary_filter(title, snippet):
    """Fast binary: is this plausibly a professor / research lab page?"""
    prompt = (
        f"Title: {title}\n"
        f"Snippet: {snippet}\n\n"
        "Is this plausibly a university professor's lab page, faculty profile, "
        "or a post about a research assistant / collaboration opportunity in AI, NLP, "
        "machine learning, or a related technical field?\n"
        'Return JSON: {"is_plausible": true/false}'
    )
    try:
        res = json.loads(cheap_complete(prompt))
        return bool(res.get("is_plausible", False))
    except Exception:
        return True  # default safe


def pass_2_professor_classify(url, page_text):
    """
    Deep-classify a professor / lab page.
    Returns structured info about the professor and their openness to collaboration.
    """
    areas_str = ", ".join(TARGET_RESEARCH_AREAS)
    prompt = (
        f"Candidate profile:\n{USER_BIO}\n\n"
        f"Page URL: {url}\n"
        f"Page text extract:\n{page_text[:5000]}\n\n"
        "Extract the following about the professor on this page:\n"
        "1. professor_name: their full name (null if not found)\n"
        "2. university: institution name (null if not found)\n"
        "3. university_domain: domain like 'uni.edu' (null if not found)\n"
        "4. research_area: one of these areas that best matches their work: " + areas_str + "\n"
        "5. research_summary: 1-sentence summary of their main research interest\n"
        "6. overlap_score: integer 0-100 — how well does the candidate's background "
        "   match this professor's research? (0 = no match, 100 = perfect match)\n"
        "7. open_to_collaboration: true if the page mentions 'looking for students', "
        "   'open positions', 'research assistant', 'we welcome', etc. else false\n"
        "8. is_blocked: true if this is MIT, Stanford, Harvard, CMU, Oxford, Cambridge, "
        "   or another elite institution that only accepts enrolled students\n\n"
        'Return JSON: {"professor_name": "...", "university": "...", "university_domain": "...", '
        '"research_area": "...", "research_summary": "...", "overlap_score": 0-100, '
        '"open_to_collaboration": true/false, "is_blocked": true/false}'
    )
    try:
        res = json.loads(cheap_complete(prompt))
        if res.get("overlap_score") is None:
            res["overlap_score"] = 0
        return res
    except Exception:
        return {"overlap_score": 0, "is_blocked": False}
