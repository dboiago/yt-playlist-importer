"""
Simple YouTube Music playlist exporter.

Usage:
  # Export a single playlist by name:
  python export_playlist.py --name "My Playlist"

  # Export all playlists:
  python export_playlist.py --all

  # Export to a specific folder:
  python export_playlist.py --all --out "C:\path\to\folder"

"""
import argparse
import csv
import json
import os
import re
import sys
from ytmusicapi import YTMusic

def _sanitize_filename(name: str) -> str:
    if not name:
        return "playlist"
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name[:240] or "playlist"

def _ensure_browser_json():
    if not os.path.exists('browser.json'):
        print("ERROR: browser.json not found. Run this script with --setup or run: ytmusicapi browser")
        sys.exit(1)
    try:
        with open('browser.json', 'r', encoding='utf-8') as f:
            headers = json.load(f)
    except Exception as e:
        print(f"ERROR reading browser.json: {e}")
        sys.exit(1)

    cookie = headers.get('Cookie') or headers.get('cookie') or ''
    if 'SAPISID' not in cookie:
        print("ERROR: browser.json missing SAPISID cookie value. Re-run setup or: ytmusicapi browser")
        sys.exit(1)

    changed = False
    if not headers.get('Origin') and not headers.get('origin'):
        headers['Origin'] = 'https://music.youtube.com'
        headers['origin'] = 'https://music.youtube.com'
        changed = True

    for k, v in list(headers.items()):
        if v is None:
            headers[k] = ''
            changed = True
        elif not isinstance(v, str):
            headers[k] = str(v)
            changed = True

    if changed:
        try:
            with open('browser.json', 'w', encoding='utf-8') as f:
                json.dump(headers, f, indent=2)
            print("Updated browser.json with defaults to avoid missing-value errors.")
        except Exception:
            pass

def _get_playlist_tracks(yt, playlist_id):
    try:
        data = yt.get_playlist(playlistId=playlist_id, limit=None)
    except Exception as e:
        print(f"ERROR fetching playlist {playlist_id}: {e}")
        return None, None
    tracks = data.get('tracks') or []
    return tracks, data.get('title') or f"playlist_{playlist_id}"

def _write_csv(out_path, tracks):
    try:
        with open(out_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Title', 'Artists', 'MediaId'])
            for t in tracks:
                title = t.get('title') or t.get('name') or ''
                artists = ''
                if t.get('artists'):
                    artists = ', '.join([a.get('name') for a in t.get('artists') if a.get('name')])
                media_id = t.get('videoId') or t.get('video_id') or t.get('id') or ''
                writer.writerow([title, artists, media_id])
        return True
    except Exception as e:
        print(f"ERROR writing CSV {out_path}: {e}")
        return False

def export_by_name(yt, name, out_dir):
    try:
        pls = yt.get_library_playlists(limit=None) or []
    except Exception as e:
        print(f"ERROR listing playlists: {e}")
        return False

    target = (name or '').strip().casefold()
    matches = [pl for pl in pls if (pl.get('title') or '').strip().casefold() == target]
    if not matches:
        matches = [pl for pl in pls if target in (pl.get('title') or '').strip().casefold()]

    if not matches:
        print(f"Playlist not found: {name}")
        return False

    pl = matches[0]
    if len(matches) > 1:
        print(f"Multiple matches found; exporting first match: {pl.get('title')}")
    pid = pl.get('playlistId')
    tracks, title = _get_playlist_tracks(yt, pid)
    if tracks is None:
        return False
    fname = _sanitize_filename(title) + '.csv'
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, fname)
    ok = _write_csv(out_path, tracks)
    if ok:
        print(f"Exported '{title}' -> {out_path}")
    return ok

def export_all(yt, out_dir):
    try:
        pls = yt.get_library_playlists(limit=None) or []
    except Exception as e:
        print(f"ERROR listing playlists: {e}")
        return False
    os.makedirs(out_dir, exist_ok=True)
    succeeded = 0
    for pl in pls:
        pid = pl.get('playlistId')
        title = pl.get('title') or pid
        tracks, _ = _get_playlist_tracks(yt, pid)
        if tracks is None:
            print(f"  - Skipped '{title}' (fetch error)")
            continue
        fname = _sanitize_filename(title) + '.csv'
        out_path = os.path.join(out_dir, fname)
        if _write_csv(out_path, tracks):
            succeeded += 1
            print(f"  ✓ {title} -> {out_path}")
        else:
            print(f"  ✗ Failed to export: {title}")
    print(f"Exported {succeeded}/{len(pls)} playlists to {out_dir}")
    return True

def setup_authentication():
    """
    Interactive setup: paste the request headers copied from DevTools (Copy → Copy request headers).
    Saves browser.json compatible with ytmusicapi in the current directory.
    """
    print("\n" + "="*60)
    print("YouTube Music Authentication Setup")
    print("="*60)
    print("\nInstructions:")
    print("1. Open music.youtube.com and make sure you're logged in")
    print("2. Open Developer Tools (F12) → Network tab")
    print("3. Refresh the page and locate a request to '/youtubei/v1/browse' or similar")
    print("4. Right-click → Copy → Copy Request Headers")
    print("\nPaste the request headers below (Ctrl+D (Unix) / Ctrl+Z (Windows) to finish) then Enter:\n")

    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass

    raw_headers = '\n'.join(lines)
    if not raw_headers.strip():
        print("No headers pasted, aborting.")
        return False

    headers = {}
    current_header = None

    for line in raw_headers.splitlines():
        line = line.strip()
        if not line:
            continue
        if ':' in line and not line.startswith(' '):
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            lk = key.lower()
            if lk == 'user-agent':
                headers['User-Agent'] = value
            elif lk == 'cookie':
                headers['Cookie'] = value
            elif lk == 'x-goog-authuser':
                headers['X-Goog-AuthUser'] = value
            elif lk == 'authorization':
                headers['Authorization'] = value
            elif lk == 'x-goog-visitor-id':
                headers['X-Goog-Visitor-Id'] = value
            else:
                headers[key] = value
            current_header = lk
        elif current_header and line:
            if current_header == 'cookie':
                headers['Cookie'] = headers.get('Cookie', '') + ' ' + line

    if not headers.get('Cookie') or 'SAPISID' not in headers.get('Cookie', ''):
        print("\n❌ ERROR: Could not find required cookies (SAPISID) in pasted headers.")
        print("Make sure you copied the full request headers including the Cookie line.")
        return False

    if not headers.get('User-Agent'):
        print("\n⚠ WARNING: User-Agent not found; using a safe default.")
        headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

    try:
        with open('browser.json', 'w', encoding='utf-8') as f:
            json.dump(headers, f, indent=2)
        print("\n✓ Authentication saved to browser.json")
        return True
    except Exception as e:
        print(f"ERROR saving browser.json: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Export YouTube Music playlist(s) to CSV")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--name', help='Export playlist by name (case-insensitive)')
    group.add_argument('--all', action='store_true', help='Export all playlists')
    parser.add_argument('--out', default='.', help='Output directory (default: current directory)')
    parser.add_argument('--setup', action='store_true', help='Run interactive authentication setup (creates browser.json)')

    args = parser.parse_args()

    if args.setup:
        ok = setup_authentication()
        if ok:
            print("Setup complete. You can now run the exporter.")
            sys.exit(0)
        else:
            print("Setup failed.")
            sys.exit(2)

    if not args.all and not args.name:
        parser.error("one of --name or --all is required unless --setup is used")

    _ensure_browser_json()
    try:
        yt = YTMusic('browser.json')
    except Exception as e:
        print(f"ERROR initializing YTMusic client: {e}")
        print("Run this script with --setup or run: ytmusicapi browser")
        sys.exit(1)

    if args.all:
        ok = export_all(yt, args.out)
        sys.exit(0 if ok else 2)
    else:
        ok = export_by_name(yt, args.name, args.out)
        sys.exit(0 if ok else 2)

if __name__ == '__main__':
    main()