import json
import os
from typing import Any, Dict, List, Optional, Tuple

from flask import jsonify, request


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"


def _service_account_info() -> Dict[str, Any]:
    raw = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not set")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Railway values sometimes get pasted with literal "\\n" or surrounding whitespace;
        # json.loads should handle valid escaped keys, so anything else is genuinely invalid.
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON")


def _google_services():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    info = _service_account_info()
    scopes = [SHEETS_SCOPE, DRIVE_SCOPE]
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    return info, sheets, drive


def _sheet_id() -> str:
    return (os.environ.get("GOOGLE_SHEET_ID") or "").strip()


def _drive_parent_folder_id() -> str:
    return (
        request.args.get("folder_id")
        or os.environ.get("GOOGLE_DRIVE_PARENT_FOLDER_ID")
        or os.environ.get("DRIVE_PARENT_FOLDER_ID")
        or ""
    ).strip()


def _list_drive_children(drive, folder_id: str, mime_type: Optional[str] = None) -> List[Dict[str, Any]]:
    clauses = [f"'{folder_id}' in parents", "trashed = false"]
    if mime_type:
        clauses.append(f"mimeType = '{mime_type}'")
    query = " and ".join(clauses)
    rows: List[Dict[str, Any]] = []
    page_token = None
    while True:
        resp = (
            drive.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, webViewLink, modifiedTime)",
                pageSize=100,
                pageToken=page_token,
                orderBy="name_natural",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        rows.extend(resp.get("files") or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return rows


def _folder_combo_summary(drive, folder: Dict[str, Any]) -> Dict[str, Any]:
    files = _list_drive_children(drive, folder["id"])
    images = [f for f in files if (f.get("mimeType") or "").startswith("image/")]
    videos = [f for f in files if (f.get("mimeType") or "").startswith("video/")]
    return {
        "folder_id": folder.get("id"),
        "folder_name": folder.get("name"),
        "image_count": len(images),
        "video_count": len(videos),
        "ready": len(images) == 1 and len(videos) == 1,
        "image_file_id": images[0]["id"] if len(images) == 1 else None,
        "image_name": images[0]["name"] if len(images) == 1 else None,
        "video_file_id": videos[0]["id"] if len(videos) == 1 else None,
        "video_name": videos[0]["name"] if len(videos) == 1 else None,
    }


def google_verify():
    """
    GET /api/google/verify
    Verifies service account, Sheet access, and optionally Drive parent folder access.
    Optional query: ?folder_id=<drive parent folder id>
    """
    sheet_id = _sheet_id()
    if not sheet_id:
        return jsonify({"ok": False, "error": "GOOGLE_SHEET_ID is not set"}), 500

    try:
        info, sheets, drive = _google_services()
        spreadsheet = (
            sheets.spreadsheets()
            .get(spreadsheetId=sheet_id, fields="spreadsheetId,properties/title,sheets(properties/title)")
            .execute()
        )
        header_resp = (
            sheets.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range="combos!1:1")
            .execute()
        )
        headers = (header_resp.get("values") or [[]])[0]

        out: Dict[str, Any] = {
            "ok": True,
            "service_account_email": info.get("client_email"),
            "sheet": {
                "id": spreadsheet.get("spreadsheetId"),
                "title": (spreadsheet.get("properties") or {}).get("title"),
                "tabs": [
                    (s.get("properties") or {}).get("title")
                    for s in spreadsheet.get("sheets", [])
                ],
                "combos_headers": headers,
            },
        }

        parent_id = _drive_parent_folder_id()
        if parent_id:
            folders = _list_drive_children(drive, parent_id, DRIVE_FOLDER_MIME)
            out["drive"] = {
                "parent_folder_id": parent_id,
                "folder_count": len(folders),
                "sample_folders": folders[:10],
            }
        else:
            out["drive"] = {
                "ok": None,
                "note": "Set GOOGLE_DRIVE_PARENT_FOLDER_ID or pass ?folder_id=... to verify Drive combo folder access.",
            }
        return jsonify(out)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


def google_drive_combos():
    """
    GET /api/google/drive-combos?folder_id=<drive parent folder id>
    Lists subfolders and detects whether each has exactly one image + one video.
    """
    parent_id = _drive_parent_folder_id()
    if not parent_id:
        return jsonify({"ok": False, "error": "folder_id query param or GOOGLE_DRIVE_PARENT_FOLDER_ID env required"}), 400

    try:
        _info, _sheets, drive = _google_services()
        folders = _list_drive_children(drive, parent_id, DRIVE_FOLDER_MIME)
        summaries = [_folder_combo_summary(drive, folder) for folder in folders]
        return jsonify(
            {
                "ok": True,
                "parent_folder_id": parent_id,
                "folder_count": len(folders),
                "ready_count": sum(1 for x in summaries if x["ready"]),
                "combos": summaries,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
