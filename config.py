import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# --- Config Variables ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
COMPOSIO_API_KEY   = os.getenv("COMPOSIO_API_KEY")
SPREADSHEET_ID     = os.getenv("SPREADSHEET_ID")

MAX_EMAILS_PER_RUN = int(os.getenv("MAX_EMAILS_PER_RUN", "10"))
SENDER_EMAIL       = os.getenv("SENDER_EMAIL", "saimim057@gmail.com")
WEEKLY_REPORT_TO   = os.getenv("WEEKLY_REPORT_CC", "hassan.zulfiqarbh@gmail.com")
USER_ID            = os.getenv("COMPOSIO_USER_ID", "pg-test-0facdbc8-c065-4664-bda2-9c9e98444c7a")
cv_path_str        = os.getenv("CV_SOURCE_PATH", r"e:\Saim documents\Academic CV.docx")
CV_SOURCE          = Path(cv_path_str) if cv_path_str else None
CV_PATH            = BASE_DIR / "assets" / "Academic_CV.docx"
STATE_DB_PATH      = BASE_DIR / "state.db"

# --- API Keys ---
_SERP_KEYS = [k for k in [
    os.getenv("SERPAPI_KEY_1"),
    os.getenv("SERPAPI_KEY_2"),
    os.getenv("SERPAPI_KEY_3"),
] if k]

_HUNTER_KEYS = [k for k in [
    os.getenv("HUNTER_API_KEY_1") or os.getenv("HUNTER_API_KEY"),
    os.getenv("HUNTER_API_KEY_2"),
    os.getenv("HUNTER_API_KEY_3"),
] if k]

_SNOV_CREDS = [
    (os.getenv("SNOV_CLIENT_ID_1"), os.getenv("SNOV_SECRET_1")),
    (os.getenv("SNOV_CLIENT_ID_2"), os.getenv("SNOV_SECRET_2")),
    (os.getenv("SNOV_CLIENT_ID_3"), os.getenv("SNOV_SECRET_3")),
]
_SNOV_CREDS = [c for c in _SNOV_CREDS if c[0] and c[1]]

# --- Models ---
FREE_MODELS = [
    "minimax/minimax-m3:free",
    "nvidia/nemotron-3.5-lightning:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "z-ai/glm-5.2:free",
]
CHEAP_MODEL  = FREE_MODELS[0]
DRAFT_MODEL  = "openai/gpt-4o-mini"

# --- Status Sets ---
SENT_STATUSES        = {"sent", "sent (verified)"}
REPLY_CHECK_STATUSES = SENT_STATUSES | {"followed up", "followed up x2"}

# --- Aggregator / social domains to ignore ---
AGGREGATOR_DOMAINS = {
    "facebook.com", "www.facebook.com", "twitter.com", "x.com",
    "linkedin.com", "instagram.com", "tiktok.com", "youtube.com",
    "medium.com", "blogspot.com", "wordpress.com",
    "researchgate.net", "academia.edu",
}

# ─────────────────────────────────────────────────────────────────────────────
# BLOCKED INSTITUTIONS
# Elite Western institutions whose labs are realistically inaccessible to a
# cold email from an undergraduate outside their program. Hard-filtered.
# ─────────────────────────────────────────────────────────────────────────────
BLOCKED_INSTITUTION_DOMAINS = {
    # USA
    "mit.edu", "stanford.edu", "harvard.edu", "cmu.edu",
    "berkeley.edu", "caltech.edu", "princeton.edu", "yale.edu",
    "columbia.edu", "cornell.edu", "upenn.edu", "nyu.edu",
    "ucla.edu", "umich.edu", "gatech.edu",
    # UK
    "ox.ac.uk", "cam.ac.uk", "imperial.ac.uk", "ucl.ac.uk",
    "ed.ac.uk", "bristol.ac.uk", "kcl.ac.uk",
    # Canada (top)
    "utoronto.ca", "mcgill.ca", "ubc.ca",
    # Corporate research labs
    "deepmind.com", "openai.com", "google.com", "microsoft.com",
    "meta.com", "apple.com", "anthropic.com",
}

BLOCKED_INSTITUTION_KEYWORDS = [
    "mit", "stanford", "harvard", "carnegie mellon", "caltech",
    "princeton", "yale", "columbia", "cornell",
    "oxford", "cambridge", "imperial college", "ucl",
    "university of edinburgh", "deepmind", "openai",
]

# ─────────────────────────────────────────────────────────────────────────────
# CANDIDATE PROFILE
# ─────────────────────────────────────────────────────────────────────────────
USER_BIO = """
Muhammad Saim — 19-year-old Computer Science undergraduate, Pakistan.

Key Projects & Skills:
- Almadina ERP: Voice-to-SQL in Urdu, processing 70k+ PKR daily volume. Demonstrates NLP for low-resource languages and enterprise AI.
- Opus Scale: AI-powered business automation startup (4 enterprise clients in month 1). Shows applied ML and system design.
- nooxe: Bootstrapped e-commerce brand; cut CAC 62% at VALOURA using ML-driven marketing optimization.
- Published economic research: AI-driven interventions for youth demographic bulges. Covers AI policy and socioeconomic modelling.
- MUN Outstanding Diplomacy Award (policy communication).
- Tech stack: Python, FastAPI, SQL, LLMs (OpenAI, local models), NLP pipelines.

Contact: saimim057@gmail.com | +92 300 1171059 | github.com/msaym22
"""

# ─────────────────────────────────────────────────────────────────────────────
# RESEARCH AREAS
# Used to match against professor research interests.
# ─────────────────────────────────────────────────────────────────────────────
TARGET_RESEARCH_AREAS = [
    "natural language processing",
    "large language models",
    "low-resource NLP",
    "speech recognition",
    "voice interfaces",
    "AI for development",
    "computational social science",
    "AI economic policy",
    "enterprise AI",
    "ERP systems",
    "information systems",
    "human-computer interaction",
    "AI applications",
    "machine learning",
    "data science for social good",
]

YEAR = datetime.now().year

# ─────────────────────────────────────────────────────────────────────────────
# PROFESSOR DISCOVERY QUERIES
# No geography priority — all universities on equal merit.
# Focused on professors who are:
#   - Active (recent publications)
#   - Open to undergraduate collaboration or RA positions
#   - Working in areas matching Saim's skills
# ─────────────────────────────────────────────────────────────────────────────
QUERY_GROUPS = [
    # ── NLP / LLM Labs ───────────────────────────────────────────────────────
    ("NLP/LLM", '"looking for students" OR "open to collaboration" NLP OR "natural language processing" professor lab undergraduate 2024 OR 2025'),
    ("NLP/LLM", '"research assistant" OR "RA position" NLP OR LLM professor university undergraduate apply'),
    ("NLP/LLM", '"join our lab" NLP OR "language model" OR "text mining" professor undergraduate open'),
    ("NLP/LLM", 'professor NLP "low-resource language" OR "Urdu" OR "multilingual" lab open undergraduate'),
    ("NLP/LLM", 'site:scholar.google.com NLP "low-resource" OR "Urdu" professor 2024 OR 2025'),

    # ── AI for Development / Policy ───────────────────────────────────────────
    ("AI Policy", '"AI for development" OR "AI policy" professor lab "undergraduate" open collaboration 2024 OR 2025'),
    ("AI Policy", '"computational social science" professor "research assistant" OR "looking for students" 2024 OR 2025'),
    ("AI Policy", '"AI governance" OR "AI ethics" professor lab "undergraduate research" open'),
    ("AI Policy", 'professor "youth" OR "demographic" "AI" policy research collaboration open 2025'),

    # ── Enterprise AI / ERP / IS ──────────────────────────────────────────────
    ("Enterprise AI", '"enterprise AI" OR "ERP" OR "information systems" professor "research assistant" undergraduate open lab'),
    ("Enterprise AI", 'professor "business intelligence" OR "decision support" AI lab open undergraduate'),
    ("Enterprise AI", '"digital transformation" professor research lab "undergraduate" OR "RA" open 2024 OR 2025'),

    # ── Voice / Speech / HCI ─────────────────────────────────────────────────
    ("Speech/HCI", '"speech recognition" OR "voice interface" OR "spoken language" professor lab open undergraduate 2024 OR 2025'),
    ("Speech/HCI", '"human-computer interaction" professor lab "looking for" OR "open positions" undergraduate'),
    ("Speech/HCI", 'professor "low-resource speech" OR "multilingual speech" lab open RA 2024 OR 2025'),

    # ── ML / Applied ML ──────────────────────────────────────────────────────
    ("Applied ML", '"machine learning" professor "open to collaborations" OR "looking for motivated students" undergraduate 2024 OR 2025'),
    ("Applied ML", '"deep learning" professor lab "research internship" OR "research assistant" undergraduate apply 2025'),
    ("Applied ML", 'professor "AI applications" lab "undergraduate research" open positions 2024 OR 2025'),

    # ── Lab pages with explicit RA openings ──────────────────────────────────
    ("Open Lab", '"openings" OR "positions available" professor lab NLP OR "machine learning" OR "AI" undergraduate'),
    ("Open Lab", 'site:cs.* professor lab "research assistant" NLP OR AI undergraduate open 2025'),
    ("Open Lab", '"we welcome" OR "we are recruiting" undergraduate "AI" OR "NLP" professor lab 2025'),

    # ── Specific non-elite university CS departments ──────────────────────────
    ("University Lab", 'Turkey university professor AI OR NLP lab "open positions" OR "looking for students" 2024 OR 2025'),
    ("University Lab", 'Malaysia university professor AI OR NLP "undergraduate research" open 2025'),
    ("University Lab", 'UAE university professor "machine learning" OR "NLP" lab open undergraduate'),
    ("University Lab", 'Saudi Arabia university professor AI research lab undergraduate open'),
    ("University Lab", 'Indonesia university professor NLP OR AI lab "undergraduate" OR "RA" open 2025'),
    ("University Lab", 'Singapore university professor AI OR NLP lab "research assistant" undergraduate open'),
    ("University Lab", 'South Korea university professor NLP OR AI lab open undergraduate collaboration'),
    ("University Lab", 'Japan university professor "natural language processing" OR AI lab undergraduate open'),
    ("University Lab", 'Pakistan university professor AI OR NLP lab open undergraduate research'),
    ("University Lab", 'Kazakhstan OR Uzbekistan university professor AI OR NLP research lab open'),
    ("University Lab", 'Germany OR Netherlands OR Austria university professor NLP OR AI lab undergraduate open 2025'),
    ("University Lab", 'Italy OR Spain university professor AI OR NLP "research assistant" undergraduate open'),
    ("University Lab", 'China university professor NLP OR AI lab "undergraduate research" open 2025'),
    ("University Lab", 'India IIT OR IIIT professor NLP OR AI lab undergraduate open 2025'),
    ("University Lab", 'Australia university professor NLP OR "machine learning" lab undergraduate open RA'),
]

# ─────────────────────────────────────────────────────────────────────────────
# EMAIL TEMPLATE HINTS
# Per-research-area strategy for Saim's cold email to the professor.
# Tone: undergraduate student, seeking paid RA primarily, open to collaboration.
# ─────────────────────────────────────────────────────────────────────────────
EMAIL_TEMPLATE_HINTS = {
    "NLP/LLM": (
        "Lead with the Almadina ERP project (Voice-to-SQL in Urdu — a real low-resource NLP system in production). "
        "Tie it directly to the professor's NLP/LLM research. "
        "Express primary interest in a paid Research Assistantship. Offer remote work."
    ),
    "AI Policy": (
        "Lead with the published economic research on AI-driven interventions for youth demographic bulges. "
        "Mention the policy communication experience (MUN). "
        "Express primary interest in a paid RA; mention openness to unpaid collaboration if RA is unavailable."
    ),
    "Enterprise AI": (
        "Lead with Almadina ERP (70k+ PKR daily, enterprise clients) and Opus Scale. "
        "Frame the request as bringing real-world enterprise AI experience into academic research. "
        "Primary ask: paid RA position."
    ),
    "Speech/HCI": (
        "Lead with Almadina ERP's Urdu voice-to-SQL feature as a concrete speech interface project. "
        "Mention low-resource speech challenges and interest in HCI. "
        "Primary ask: paid RA or research internship."
    ),
    "Applied ML": (
        "Highlight Python/ML stack, Almadina ERP, and Opus Scale as applied ML projects. "
        "Show genuine interest in the professor's specific ML research area. "
        "Primary ask: paid RA. Offer to contribute to an ongoing project."
    ),
    "Open Lab": (
        "Lead with the most relevant project to the lab's focus area. "
        "Show you researched the lab specifically. "
        "Primary ask: paid RA. Be direct and professional."
    ),
    "University Lab": (
        "Be warm but professional. Reference a specific paper or project of the professor. "
        "Explain how Saim's background (Almadina ERP, published research) aligns with their work. "
        "Primary ask: paid RA. Open to remote arrangement."
    ),
}
