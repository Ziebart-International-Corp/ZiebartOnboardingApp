"""
One-off script to set training_videos.file_path to Vercel Blob (or any) URLs.
Run from project root with .env set (e.g. DATABASE_URL for Neon).

Examples:
  python update_training_video_urls.py --id 1 --url "https://xxx.public.blob.vercel-storage.com/harassment%20video.mp4"
  python update_training_video_urls.py --title "harassment video.mp4" --url "https://..."
"""
import argparse
import os
import sys

# Load .env and use app config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from config import SQLALCHEMY_DATABASE_URI
from sqlalchemy import create_engine, text

def main():
    p = argparse.ArgumentParser(description="Update training_videos.file_path to a URL (e.g. Vercel Blob).")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", type=int, help="Video id to update")
    g.add_argument("--title", type=str, help="Video title (or filename) to match and update")
    p.add_argument("--url", type=str, required=True, help="Full URL (e.g. Blob public URL)")
    p.add_argument("--dry-run", action="store_true", help="Only print what would be updated")
    args = p.parse_args()

    engine = create_engine(SQLALCHEMY_DATABASE_URI)
    with engine.connect() as conn:
        if args.id is not None:
            r = conn.execute(text("SELECT id, title, file_path FROM training_videos WHERE id = :id"), {"id": args.id})
        else:
            r = conn.execute(
                text("SELECT id, title, file_path FROM training_videos WHERE title = :t OR original_filename = :t OR filename = :t"),
                {"t": args.title}
            )
        rows = r.fetchall()
        if not rows:
            print("No matching video found.")
            return 1
        if len(rows) > 1:
            print("Multiple videos matched; use --id to target one:", [r[0] for r in rows])
            return 1
        vid, title, old_path = rows[0]
        print(f"Video id={vid} title={title!r}")
        print(f"  Old file_path: {old_path}")
        print(f"  New URL:       {args.url}")
        if args.dry_run:
            print("  (dry-run: no change made)")
            return 0
        conn.execute(text("UPDATE training_videos SET file_path = :url WHERE id = :id"), {"url": args.url, "id": vid})
        conn.commit()
        print("  Updated.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
