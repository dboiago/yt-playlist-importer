import csv
import json
import os
import sys
import time
import re
import logging
from ytmusicapi import YTMusic

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Security warning
SECURITY_WARNING = """
⚠️  SECURITY WARNING ⚠️
browser.json contains authentication cookies (SAPISID, etc.)
Treat it like a password:
- Add browser.json to .gitignore
- Never commit or share browser.json
- Keep file permissions restricted (chmod 600 on Unix)
"""

def setup_authentication():
    """
    Interactive setup for YouTube Music authentication.
    Creates browser.json from request headers.
    """
    print("\n" + "="*70)
    print("YouTube Music Authentication Setup")
    print("="*70)
    print("\nInstructions:")
    print("1. Open YouTube Music (music.youtube.com) in your browser")
    print("2. Make sure you're logged in")
    print("3. Open Developer Tools (F12)")
    print("4. Go to the Network tab")
    print("5. Refresh the page")
    print("6. Find a request to 'music.youtube.com/youtubei/v1/browse'")
    print("7. Right-click → Copy → Copy Request Headers")
    print("\nPaste the request headers below:")
    print("(Press Ctrl+D or Ctrl+Z (Windows) when done)\n")
    
    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass
    
    raw_headers = '\n'.join(lines)
    
    # Parse raw request headers format
    headers = {}
    current_header = None
    
    for line in raw_headers.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # Check if this is a header line (contains ':')
        if ':' in line and not line.startswith(' '):
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            
            # Map header names to what ytmusicapi expects
            if key.lower() == 'user-agent':
                headers['User-Agent'] = value
            elif key.lower() == 'cookie':
                headers['Cookie'] = value
            elif key.lower() == 'x-goog-authuser':
                headers['X-Goog-AuthUser'] = value
            elif key.lower() == 'authorization':
                headers['Authorization'] = value
            elif key.lower() == 'x-goog-visitor-id':
                headers['X-Goog-Visitor-Id'] = value
            
            current_header = key
        elif current_header and line:
            # Continuation of previous header (multi-line)
            if current_header.lower() == 'cookie':
                headers['Cookie'] += ' ' + line
    
    # Validate we have the required headers
    if not headers.get('Cookie') or 'SAPISID' not in headers.get('Cookie', ''):
        print("\n❌ ERROR: Could not find required cookies!")
        print("Make sure you copied the full request headers including the Cookie line.")
        print("The Cookie should contain SAPISID.")
        return False
    
    if not headers.get('User-Agent'):
        print("\n⚠ WARNING: User-Agent not found, using default")
        headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    
    # Save to browser.json
    with open('browser.json', 'w') as f:
        json.dump(headers, f, indent=2)
    
    print("\n✓ Authentication saved to browser.json")
    print(f"✓ Found {len(headers)} headers")
    return True

def search_youtube_music(yt, title, artist):
    """
    Search YouTube Music for a song by title and artist.
    Returns the best matching video ID, or None if not found.
    """
    try:
        query = f"{title} {artist}"
        results = yt.search(query, filter='songs', limit=5)
        
        if not results:
            return None
        
        # Return the first result's video ID
        # Could be made smarter with fuzzy matching, but first result is usually correct
        return results[0].get('videoId')
    except Exception as e:
        print(f"    Search error: {e}")
        return None

def parse_spotify_playlist(url):
    """
    Parse a Spotify playlist URL and return playlist info.
    Note: This requires the spotipy library and Spotify API credentials.
    """
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
        
        # Extract playlist ID from URL
        playlist_id = url.split('playlist/')[-1].split('?')[0]
        
        # Initialize Spotify client
        # Users need to set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET env vars
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials())
        
        # Get playlist details
        playlist = sp.playlist(playlist_id)
        
        songs = []
        for item in playlist['tracks']['items']:
            track = item['track']
            if track:
                songs.append({
                    'title': track['name'],
                    'artists': ', '.join([artist['name'] for artist in track['artists']]),
                    'videoId': None  # Will search for this
                })
        
        return {
            'name': playlist['name'],
            'songs': songs
        }
    except ImportError:
        print("ERROR: spotipy library not installed!")
        print("Install with: pip install spotipy")
        print("Set environment variables: SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET")
        return None
    except Exception as e:
        print(f"ERROR parsing Spotify playlist: {e}")
        return None

def import_playlist_from_csv(yt, csv_file):
    """
    Import playlists from CSV file.
    Supports multiple formats:
    - Kreate format: PlaylistBrowseId, PlaylistName, MediaId, Title, Artists, Duration, ThumbnailUrl
    - Simple format: Title, Artist (will search YouTube Music)
    - URL format: URL (extracts video ID)
    """
    playlists = {}
    
    print(f"\nReading CSV file: {csv_file}")
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            # Ensure theres always a list for membership checks
            if headers is None:
                headers = []
            
            # Detect CSV format
            has_mediaid = 'MediaId' in headers
            has_playlistname = 'PlaylistName' in headers
            has_url = 'URL' in headers or 'url' in headers
            
            # Determine playlist name
            if has_playlistname:
                default_playlist_name = None
            else:
                # Use filename as playlist name
                default_playlist_name = os.path.splitext(os.path.basename(csv_file))[0]
            
            for row in reader:
                # Get playlist name
                if has_playlistname:
                    playlist_name = row['PlaylistName'].strip()
                else:
                    playlist_name = default_playlist_name
                
                if not playlist_name:
                    continue
                
                # Get video ID (try multiple methods)
                video_id = None
                title = row.get('Title', '').strip()
                artists = row.get('Artists', '').strip() or row.get('Artist', '').strip()
                
                # Method 1: Direct MediaId/VideoId (use .get to avoid KeyError / None.strip())
                if has_mediaid:
                    video_id = (row.get('MediaId') or '').strip()
                elif 'VideoId' in headers:
                    video_id = (row.get('VideoId') or '').strip()
                
                # Method 2: Parse from URL
                if not video_id and has_url:
                    url = row.get('URL', '') or row.get('url', '')
                    if url:
                        # Extract video ID from YouTube URL
                        match = re.search(r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})', url)
                        if match:
                            video_id = match.group(1)
                
                # Method 3: Search by title/artist (fallback)
                search_needed = not video_id and title
                
                if playlist_name not in playlists:
                    playlists[playlist_name] = []
                
                playlists[playlist_name].append({
                    'videoId': video_id,
                    'title': title,
                    'artists': artists,
                    'search_needed': search_needed
                })
        
        print(f"✓ Found {len(playlists)} playlist(s) with {sum(len(songs) for songs in playlists.values())} total songs")
        return playlists
    
    except Exception as e:
        print(f"ERROR reading CSV: {e}")
        import traceback
        traceback.print_exc()
        return None

def import_playlist(yt, playlist_name, songs, append=True):
    """
    Import a single playlist to YouTube Music.
    If append=True and playlist exists, adds songs to existing playlist.
    If append=False, always creates a new playlist.
    """
    print(f"\n{'='*70}")
    print(f"Processing: {playlist_name} ({len(songs)} songs)")
    print('='*70)
    
    try:
        playlist_id = None
        
        # Check if playlist already exists (if append mode)
        if append:
            print("  Checking for existing playlist...")
            try:
                existing_playlists = yt.get_library_playlists(limit=None)
                for pl in existing_playlists:
                    existing_title = (pl.get('title') or '').strip().casefold()
                    target_title = (playlist_name or '').strip().casefold()
                    if existing_title == target_title:
                        playlist_id = pl.get('playlistId')
                        print(f"✓ Found existing playlist (ID: {playlist_id})")
                        print(f"  Will append songs to existing playlist")
                        break
            except Exception as e:
                print(f"  Warning: Could not check for existing playlists: {e}")
        
        # Create new playlist if doesn't exist
        if not playlist_id:
            playlist_id = yt.create_playlist(
                title=playlist_name,
                description=f"Imported playlist - {len(songs)} songs"
            )
            print(f"✓ Created new playlist (ID: {playlist_id})")
        
        successful = 0
        failed = 0
        searched = 0
        skipped = 0
        failed_songs = []
        
        for i, song in enumerate(songs, 1):
            try:
                video_id = song['videoId']
                
                # If no video ID, search for it
                if not video_id and song.get('search_needed'):
                    print(f"  Searching: {song['title']} - {song['artists']}")
                    video_id = search_youtube_music(yt, song['title'], song['artists'])
                    searched += 1
                    
                    if not video_id:
                        raise Exception("Song not found in search")
                
                if not video_id:
                    raise Exception("No video ID available")
                
                # Add to playlist
                result = yt.add_playlist_items(
                    playlistId=playlist_id,
                    videoIds=[video_id],
                    duplicates=False
                )
                successful += 1
                
                # Progress indicator
                if i % 10 == 0 or i == len(songs):
                    status = f"  Progress: {i}/{len(songs)} songs"
                    if searched > 0:
                        status += f" ({searched} searched)"
                    print(status)
                
                # Rate limiting
                time.sleep(0.3 if not song.get('search_needed') else 0.5)
                
            except Exception as e:
                error_msg = str(e)
                
                # Check for success reported as error (ytmusicapi quirk)
                if 'STATUS_SUCCEEDED' in error_msg:
                    successful += 1
                # Check if song already in playlist
                elif 'already' in error_msg.lower() or 'duplicate' in error_msg.lower():
                    skipped += 1
                else:
                    failed += 1
                    failed_songs.append({
                        'title': song['title'],
                        'artists': song['artists'],
                        'error': error_msg
                    })
                
                if failed > 0 and failed % 10 == 0:
                    print(f"  ⚠ {failed} songs failed so far...")
        
        print(f"\n✓ Completed '{playlist_name}'")
        print(f"  ✓ Successfully added: {successful}/{len(songs)} songs")
        if searched > 0:
            print(f"  🔍 Songs found by search: {searched}")
        if skipped > 0:
            print(f"  ⏭ Skipped (already in playlist): {skipped}")
        if failed > 0:
            print(f"  ✗ Failed: {failed} songs")
            print(f"\nFailed songs:")
            for fs in failed_songs[:10]:
                print(f"  - {fs['title']} by {fs['artists']}")
                print(f"    Error: {fs['error']}")
            if len(failed_songs) > 10:
                print(f"  ... and {len(failed_songs) - 10} more")
        
        return True
        
    except Exception as e:
        print(f"✗ ERROR processing playlist '{playlist_name}': {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """
    Main entry point for the playlist importer.
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Import playlists to YouTube Music from CSV files or Spotify URLs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
EXAMPLES:
  # Import single CSV
  python playlist_importer.py playlist.csv
  
  # Import all CSVs in directory
  python playlist_importer.py *.csv
  
  # Import from Spotify (requires spotipy and API credentials)
  python playlist_importer.py --spotify https://open.spotify.com/playlist/...
  
  # Setup authentication interactively
  python playlist_importer.py --setup

AUTHENTICATION:
  First time setup: python playlist_importer.py --setup
  Or manually run: ytmusicapi browser
        '''
    )
    
    parser.add_argument('files', nargs='*', help='CSV file(s) to import')
    parser.add_argument('--setup', action='store_true', help='Run interactive authentication setup')
    parser.add_argument('--spotify', help='Import from Spotify playlist URL')
    parser.add_argument('--no-append', action='store_true', help='Always create new playlists instead of appending to existing ones')
    
    args = parser.parse_args()
    
    # Determine append mode (default is True, unless --no-append is specified)
    append_mode = not args.no_append
    
    # Handle setup mode
    if args.setup:
        if setup_authentication():
            print("\n✓ Setup complete! You can now import playlists.")
        else:
            print("\n✗ Setup failed. Please try again.")
        return
    
    # Check for authentication
    if not os.path.exists('browser.json'):
        print("ERROR: browser.json not found!")
        print("\nRun authentication setup first:")
        print("  python playlist_importer.py --setup")
        print("\nOr manually run: ytmusicapi browser")
        sys.exit(1)
    
    # Initialize YouTube Music client
    try:
        yt = YTMusic('browser.json')
        print("✓ Successfully authenticated with YouTube Music")
    except Exception as e:
        print(f"ERROR initializing YouTube Music: {e}")
        print("\nTry running authentication setup again:")
        print("  python playlist_importer.py --setup")
        sys.exit(1)
    
    # Handle Spotify import
    if args.spotify:
        print(f"\nImporting from Spotify: {args.spotify}")
        playlist_data = parse_spotify_playlist(args.spotify)
        if playlist_data:
            import_playlist(yt, playlist_data['name'], playlist_data['songs'], append=append_mode)
        return
    
    # Handle CSV imports
    if not args.files:
        parser.print_help()
        sys.exit(1)
    
    # Collect CSV files
    import glob
    csv_files = []
    for arg in args.files:
        if os.path.isdir(arg):
            csv_files.extend(glob.glob(os.path.join(arg, "*.csv")))
        elif os.path.isfile(arg):
            csv_files.append(arg)
        elif '*' in arg:
            csv_files.extend(glob.glob(arg))
    
    if not csv_files:
        print("ERROR: No CSV files found!")
        sys.exit(1)
    
    print(f"\n{'='*70}")
    print(f"Found {len(csv_files)} CSV file(s) to import")
    print('='*70)
    for f in csv_files:
        print(f"  - {f}")
    
    # Process each CSV file
    total_playlists = 0
    for i, csv_file in enumerate(csv_files, 1):
        print(f"\n{'#'*70}")
        print(f"# Processing file {i}/{len(csv_files)}: {os.path.basename(csv_file)}")
        print(f"{'#'*70}")
        
        playlists = import_playlist_from_csv(yt, csv_file)
        if playlists:
            for playlist_name, songs in playlists.items():
                if import_playlist(yt, playlist_name, songs, append=append_mode):
                    total_playlists += 1
    
    print("\n" + "="*70)
    print(f"ALL COMPLETE - Imported {total_playlists} playlists from {len(csv_files)} file(s)")
    print("="*70)

if __name__ == "__main__":
    main()