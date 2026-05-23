import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import jsonify, request


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
DRIVE_DOWNLOAD = "https://drive.google.com/uc?export=download&id="
COMBOS_HEADERS = [
    "folder_id",
    "folder_name",
    "image_file_id",
    "video_file_id",
    "combo_label",
    "status",
    "adset_ids",
    "launch_date",
    "spend_inr",
    "purchases",
    "roas",
    "last_insights_at",
    "last_action",
    "notes",
]


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


def _drive_videos_folder_id() -> str:
    return (
        request.args.get("folder_id")
        or os.environ.get("VIDEOS_FOLDER")
        or os.environ.get("META_AD_VIDEOS_DRIVE_FOLDER_ID")
        or os.environ.get("GOOGLE_DRIVE_PARENT_FOLDER_ID")
        or ""
    ).strip()


def _row_from_combo(combo: Dict[str, Any], status: str, note: str = "") -> List[str]:
    return [
        combo.get("folder_id") or "",
        combo.get("folder_name") or "",
        combo.get("image_file_id") or "",
        combo.get("video_file_id") or "",
        f"Drive folder {combo.get('folder_name') or ''}".strip(),
        status,
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        note,
    ]


def _sheet_values(sheets, sheet_id: str, range_name: str) -> List[List[str]]:
    resp = sheets.spreadsheets().values().get(spreadsheetId=sheet_id, range=range_name).execute()
    return resp.get("values") or []


def _cell(row: List[str], idx: int) -> str:
    return row[idx].strip() if len(row) > idx and isinstance(row[idx], str) else ""


def _ensure_combos_headers(sheets, sheet_id: str) -> None:
    rows = _sheet_values(sheets, sheet_id, "combos!1:1")
    if rows and rows[0][: len(COMBOS_HEADERS)] == COMBOS_HEADERS:
        return
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="combos!1:1",
        valueInputOption="RAW",
        body={"values": [COMBOS_HEADERS]},
    ).execute()


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


def google_sync_combos():
    """
    POST /api/google/sync-combos
    Body:
      {
        "folder_id": "<Drive parent folder>",
        "used_folder_names": ["2"],
        "used_status": "used",
        "used_note": "Launched manually yesterday as separate image/video ads"
      }

    Idempotently appends missing Drive combo folders to the combos sheet.
    Existing rows are not overwritten.
    """
    data = request.get_json(force=True, silent=True) or {}
    parent_id = (data.get("folder_id") or _drive_parent_folder_id()).strip()
    if not parent_id:
        return jsonify({"ok": False, "error": "folder_id body/query/env required"}), 400

    sheet_id = _sheet_id()
    if not sheet_id:
        return jsonify({"ok": False, "error": "GOOGLE_SHEET_ID is not set"}), 500

    used_names = {str(x).strip() for x in data.get("used_folder_names", []) if str(x).strip()}
    used_status = str(data.get("used_status") or "used").strip()
    used_note = str(data.get("used_note") or "").strip()

    try:
        _info, sheets, drive = _google_services()
        _ensure_combos_headers(sheets, sheet_id)

        folders = _list_drive_children(drive, parent_id, DRIVE_FOLDER_MIME)
        summaries = [_folder_combo_summary(drive, folder) for folder in folders]

        existing_rows = _sheet_values(sheets, sheet_id, "combos!A2:N")
        existing_folder_ids = {row[0] for row in existing_rows if row and row[0]}
        existing_folder_names = {row[1] for row in existing_rows if len(row) > 1 and row[1]}

        append_rows = []
        skipped_existing = []
        for combo in summaries:
            folder_id = combo.get("folder_id") or ""
            folder_name = combo.get("folder_name") or ""
            if folder_id in existing_folder_ids or folder_name in existing_folder_names:
                skipped_existing.append(folder_name)
                continue
            if not combo.get("ready"):
                status = "needs_review"
                note = f"Expected exactly 1 image + 1 video; found {combo.get('image_count')} image(s), {combo.get('video_count')} video(s)"
            elif folder_name in used_names:
                status = used_status
                note = used_note or "Already launched before queue initialization"
            else:
                status = "queued"
                note = ""
            append_rows.append(_row_from_combo(combo, status, note))

        if append_rows:
            sheets.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range="combos!A:N",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": append_rows},
            ).execute()

        updated_existing = []
        if used_names:
            updates = []
            for row_num, row in enumerate(existing_rows, start=2):
                folder_name = row[1] if len(row) > 1 else ""
                if folder_name not in used_names:
                    continue
                note = used_note or "Already launched before queue initialization"
                updates.append({"range": f"combos!F{row_num}", "values": [[used_status]]})
                updates.append({"range": f"combos!N{row_num}", "values": [[note]]})
                updated_existing.append(folder_name)
            if updates:
                sheets.spreadsheets().values().batchUpdate(
                    spreadsheetId=sheet_id,
                    body={"valueInputOption": "RAW", "data": updates},
                ).execute()

        return jsonify(
            {
                "ok": True,
                "parent_folder_id": parent_id,
                "found_count": len(summaries),
                "appended_count": len(append_rows),
                "updated_existing_used": updated_existing,
                "skipped_existing": skipped_existing,
                "used_folder_names": sorted(used_names),
                "appended_rows": append_rows,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


def google_pick_next_combo():
    """
    POST /api/google/pick-next-combo
    Atomically-ish locks the first queued combo by setting status=processing.

    Body (optional):
      {
        "lock_note": "creative pipeline",
        "status_from": "queued",
        "status_to": "processing"
      }
    """
    data = request.get_json(force=True, silent=True) or {}
    sheet_id = _sheet_id()
    if not sheet_id:
        return jsonify({"ok": False, "error": "GOOGLE_SHEET_ID is not set"}), 500

    status_from = str(data.get("status_from") or "queued").strip().lower()
    status_to = str(data.get("status_to") or "processing").strip()
    lock_note = str(data.get("lock_note") or "locked by pick-next-combo").strip()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        _info, sheets, _drive = _google_services()
        _ensure_combos_headers(sheets, sheet_id)

        rows = _sheet_values(sheets, sheet_id, "combos!A2:N")
        candidates = []
        for row_num, row in enumerate(rows, start=2):
            status = _cell(row, 5).lower()
            folder_id = _cell(row, 0)
            folder_name = _cell(row, 1)
            image_file_id = _cell(row, 2)
            video_file_id = _cell(row, 3)
            if status != status_from:
                continue
            if not (folder_id and folder_name and image_file_id and video_file_id):
                continue
            candidates.append((row_num, row))

        if not candidates:
            return jsonify(
                {
                    "ok": True,
                    "picked": False,
                    "message": f"No combo rows with status '{status_from}' and complete image/video IDs.",
                }
            )

        for row_num, row in candidates:
            # Race guard: re-read just this row before updating it.
            live = _sheet_values(sheets, sheet_id, f"combos!A{row_num}:N{row_num}")
            live_row = live[0] if live else []
            if _cell(live_row, 5).lower() != status_from:
                continue

            note = f"{lock_note} at {now}"
            updates = [
                {"range": f"combos!F{row_num}", "values": [[status_to]]},
                {"range": f"combos!L{row_num}", "values": [[now]]},
                {"range": f"combos!M{row_num}", "values": [[f"locked:{status_to}"]]},
                {"range": f"combos!N{row_num}", "values": [[note]]},
            ]
            sheets.spreadsheets().values().batchUpdate(
                spreadsheetId=sheet_id,
                body={"valueInputOption": "RAW", "data": updates},
            ).execute()

            picked = {
                "row_number": row_num,
                "folder_id": _cell(live_row, 0),
                "folder_name": _cell(live_row, 1),
                "image_file_id": _cell(live_row, 2),
                "video_file_id": _cell(live_row, 3),
                "combo_label": _cell(live_row, 4),
                "previous_status": _cell(live_row, 5),
                "status": status_to,
                "locked_at": now,
                "notes": note,
            }
            return jsonify({"ok": True, "picked": True, "combo": picked})

        return jsonify(
            {
                "ok": True,
                "picked": False,
                "message": "Queued candidates were already claimed by another process.",
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


def google_drive_videos():
    """
    GET /api/drive/videos?folder_id=<optional>
    Lists source videos available for the dashboard Video Brain.
    """
    folder_id = _drive_videos_folder_id()
    if not folder_id:
        return jsonify({"ok": False, "error": "VIDEOS_FOLDER or folder_id required"}), 400
    try:
        _info, _sheets, drive = _google_services()
        rows = _list_drive_children(drive, folder_id)
        videos = []
        for row in rows:
            mime = row.get("mimeType") or ""
            if not mime.startswith("video/"):
                continue
            file_id = row.get("id") or ""
            videos.append(
                {
                    "id": file_id,
                    "name": row.get("name") or "",
                    "url": DRIVE_DOWNLOAD + file_id,
                    "thumbnail": f"https://drive.google.com/thumbnail?id={file_id}&sz=w800",
                    "mime_type": mime,
                    "webViewLink": row.get("webViewLink") or "",
                    "modifiedTime": row.get("modifiedTime") or "",
                }
            )
        return jsonify({"ok": True, "folder_id": folder_id, "count": len(videos), "videos": videos})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
