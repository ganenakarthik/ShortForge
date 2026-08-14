"""Upload queued Shorts to YouTube via the Data API v3 (resumable upload).

GATE: requires projects/daily/client_secret.json (OAuth client, Desktop app)
from https://console.cloud.google.com/apis/credentials â€” create one, download
it, place it here. First run opens a browser for one-time consent.
Until then this script only prints setup instructions and uploads nothing.
Honest status: written to the official API pattern; not yet end-to-end tested
on this machine (no client_secret.json present).

Usage:
  python projects/daily/upload_youtube.py            # upload all "ready" entries
  python projects/daily/upload_youtube.py --entry 1  # upload only entry index 1
"""

import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(ROOT, "queue", "publish_queue.json")
CLIENT_SECRET = os.path.join(ROOT, "client_secret.json")
TOKEN = os.path.join(ROOT, "queue", "token.json")
# Full scope: upload + update (privacy flips, edits). Re-consent needed once
# after changing this.
SCOPE = "https://www.googleapis.com/auth/youtube"


def _get_creds():
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    creds = None
    if os.path.exists(TOKEN):
        creds = Credentials.from_authorized_user_file(TOKEN, ["https://www.googleapis.com/auth/youtube"])
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError("no valid token; run without --publish once to authorize")
    return build("youtube", "v3", credentials=creds)


def _safe_delete(path: str, attempts: int = 5, delay: float = 2.0) -> bool:
    """Best-effort delete with retries (the file can be briefly locked by
    Windows media handlers / AV after upload)."""
    for i in range(attempts):
        try:
            if os.path.exists(path):
                os.remove(path)
            return True
        except OSError:
            if i == attempts - 1:
                return False
            time.sleep(delay)
    return True


def _sweep_leftovers(queue):
    """Retry deleting mp4s from previous runs whose delete got locked."""
    cleaned = 0
    for entry in queue:
        if entry.get("status") != "uploaded" or not entry.get("file"):
            continue
        path = os.path.join(os.path.dirname(os.path.dirname(ROOT)), entry["file"])
        if os.path.exists(path) and _safe_delete(path):
            cleaned += 1
            print(f"[sweep] removed leftover: {entry['file']}")
    return cleaned


def main():
    publish_only = "--publish" in sys.argv
    entry_filter = None
    if len(sys.argv) > 2 and sys.argv[1] == "--entry":
        entry_filter = int(sys.argv[2])

    if not os.path.exists(CLIENT_SECRET):
        print("=" * 72)
        print("YouTube upload NOT configured yet. Nothing uploaded.")
        print("")
        print("One-time setup (about 10 minutes):")
        print("1. https://console.cloud.google.com/apis/credentials -> Create Credentials ->")
        print("   OAuth client ID -> Desktop app -> download JSON")
        print("2. Save it as:  projects\\daily\\client_secret.json")
        print("3. Enable the YouTube Data API v3 for the same project.")
        print("4. Re-run this script once to authorize (browser opens, allow once).")
        print("=" * 72)
        return 0

    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        print("Missing deps. Run:  .venv\\Scripts\\pip install google-api-python-client google-auth-oauthlib")
        return 1

    creds = None
    if os.path.exists(TOKEN):
        creds = Credentials.from_authorized_user_file(TOKEN, ["https://www.googleapis.com/auth/youtube"])
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET, [SCOPE])
            creds = flow.run_local_server(port=0)
        with open(TOKEN, "w") as f:
            f.write(creds.to_json())

    youtube = build("youtube", "v3", credentials=creds)
    with open(QUEUE, "r", encoding="utf-8") as f:
        queue = json.load(f)

    if not publish_only:
        _sweep_leftovers(queue)

    if publish_only:
        # Flip already-uploaded videos to public (e.g. after a private run)
        flipped = 0
        skipped = 0
        for i, entry in enumerate(queue, start=1):
            if entry_filter and i != entry_filter:
                continue
            if not entry.get("video_id"):
                continue
            try:
                req = youtube.videos().update(
                    part="status",
                    body={"id": entry["video_id"],
                          "status": {"privacyStatus": os.environ.get("YT_PRIVACY", "public")}})
                resp = req.execute()
                print(f"[{i}] {entry['title'][:50]} -> {resp['status']['privacyStatus']} "
                      f"(https://youtu.be/{entry['video_id']})")
                flipped += 1
            except Exception as exc:
                # video deleted off the channel or never existed; keep going
                skipped += 1
                print(f"[{i}] skip (video not found): {entry['video_id']} — {exc}")
        print(f"done, {flipped} set to {os.environ.get('YT_PRIVACY', 'public')}, {skipped} skipped")
        return 0

    uploaded = 0
    for i, entry in enumerate(queue, start=1):
        if entry_filter and i != entry_filter:
            continue
        if entry.get("status") != "ready":
            print(f"[{i}] skip (status={entry.get('status')})")
            continue
        path = os.path.join(os.path.dirname(os.path.dirname(ROOT)), entry["file"])
        if not os.path.exists(path):
            print(f"[{i}] file missing: {path}")
            continue
        path = os.path.abspath(path)
        body = {
            "snippet": {
                "title": entry["title"],
                "description": entry["description"],
                "tags": ["ai", "explained", "shorts"],
                "categoryId": "27",
            },
            "status": {
                "privacyStatus": os.environ.get("YT_PRIVACY", "public"),
                "selfDeclaredMadeForKids": False,
                "selfDeclaredContentRating": None,
            },
        }
        media = MediaFileUpload(path, chunksize=-1, resumable=True)
        req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        print(f"[{i}] uploading: {entry['title']} ...")
        response = req.execute()
        print(f"[{i}] uploaded: https://youtu.be/{response['id']}  (status={response['status']['uploadStatus']})")
        entry["status"] = "uploaded"
        entry["video_id"] = response["id"]
        uploaded += 1

        # Post-upload cleanup: free storage. Delete the rendered mp4 and the
        # staged assets in the composer's public dir. The mp4 can be briefly
        # locked on Windows — retry, and the startup sweep catches leftovers.
        try:
            if not _safe_delete(path):
                print(f"[{i}] warn: could not delete (locked): {path} — will retry next run")
        except OSError as exc:
            print(f"[{i}] warn: could not delete {path}: {exc}")
        try:
            job_dir = f"daily-{entry.get('date')}-{entry.get('index')}"
            staged = os.path.join(os.path.dirname(os.path.dirname(ROOT)),
                                  "remotion-composer", "public", job_dir)
            if os.path.isdir(staged):
                shutil.rmtree(staged, ignore_errors=True)
                print(f"[{i}] deleted staged assets: {job_dir}")
        except Exception as exc:
            print(f"[{i}] warn: could not clean staged assets: {exc}")

    if uploaded:
        with open(QUEUE, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2)
        print(f"done, {uploaded} uploaded. Privacy: {os.environ.get('YT_PRIVACY', 'private')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

