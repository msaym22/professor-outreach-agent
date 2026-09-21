"""
sheet_utils.py — Google Sheets logging for the professor outreach agent.

Sheet columns:
  A: Research Area
  B: Professor Name
  C: University
  D: Lab / Faculty URL
  E: Email
  F: Status
  G: Timestamp
  H: Overlap Score (0-100)
  I: Research Summary
  J: Gmail Thread ID
"""
from datetime import datetime
from composio import Composio
from config import COMPOSIO_API_KEY, BASE_DIR, USER_ID, SPREADSHEET_ID
from tenacity import retry, stop_after_attempt, wait_exponential

_composio_client = None


def _get_composio_client():
    global _composio_client
    if _composio_client is None:
        _composio_client = Composio(
            api_key=COMPOSIO_API_KEY,
            dangerously_allow_auto_upload_download_files=True,
            file_upload_dirs=[str(BASE_DIR / "assets"), str(BASE_DIR)],
        )
    return _composio_client


def _normalize_tool_arguments(slug, arguments):
    arguments = dict(arguments or {})
    sheet_slugs = (
        "GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND",
        "GOOGLESHEETS_VALUES_UPDATE",
        "GOOGLESHEETS_UPDATE_VALUES_BATCH",
    )
    if slug in sheet_slugs:
        if "spreadsheetId" not in arguments and "spreadsheet_id" in arguments:
            arguments["spreadsheetId"] = arguments.pop("spreadsheet_id")
        if "valueInputOption" not in arguments and "value_input_option" in arguments:
            arguments["valueInputOption"] = arguments.pop("value_input_option")
    return arguments


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def safe_execute(slug, arguments):
    try:
        result = _get_composio_client().tools.execute(
            slug,
            arguments=_normalize_tool_arguments(slug, arguments),
            user_id=USER_ID,
            dangerously_skip_version_check=True,
        )
        if isinstance(result, dict) and "data" in result and "successful" in result:
            if result.get("successful") is False:
                print(f"Error executing {slug}: {result.get('error')}")
                return {}
            data = result.get("data")
            return data if isinstance(data, dict) else result
        return result
    except Exception as e:
        print(f"Error executing {slug}: {e}")
        return {}


def append_sheet_row(
    research_area, prof_name, university, lab_url,
    email, status, overlap_score=0, research_summary="", thread_id=""
):
    safe_execute(
        "GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND",
        {
            "spreadsheet_id": SPREADSHEET_ID,
            "range": "Sheet1!A:J",
            "values": [[
                research_area,                              # A
                prof_name,                                  # B
                university,                                 # C
                lab_url,                                    # D
                email,                                      # E
                status,                                     # F
                datetime.now().strftime("%Y-%m-%d %H:%M"), # G
                overlap_score,                             # H
                research_summary,                          # I
                thread_id,                                 # J
            ]],
            "value_input_option": "USER_ENTERED",
        },
    )


def update_sheet_status(row_index, new_status):
    sheet_row = row_index + 2
    safe_execute(
        "GOOGLESHEETS_VALUES_UPDATE",
        {
            "spreadsheet_id": SPREADSHEET_ID,
            "range": f"Sheet1!F{sheet_row}",
            "values": [[new_status]],
            "value_input_option": "USER_ENTERED",
        },
    )


def extract_sheet_rows(sheet_data):
    raw_values = []
    if isinstance(sheet_data, dict):
        raw_values = sheet_data.get("values", []) or []
        if not raw_values:
            value_ranges = sheet_data.get("valueRanges", []) or []
            if value_ranges and isinstance(value_ranges[0], dict):
                raw_values = value_ranges[0].get("values", []) or []
    return raw_values if isinstance(raw_values, list) else []


def fetch_sheet_rows():
    sheet_data = safe_execute(
        "GOOGLESHEETS_BATCH_GET",
        {"spreadsheet_id": SPREADSHEET_ID, "ranges": ["Sheet1!A2:J2000"]},
    )
    return extract_sheet_rows(sheet_data)
