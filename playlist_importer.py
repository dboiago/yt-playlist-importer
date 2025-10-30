import csv
import json
import os
import sys
import time
import re
import logging
from functools import wraps
from ytmusicapi import YTMusic

# Security warning
SECURITY_WARNING = """
⚠️  SECURITY WARNING ⚠️
browser.json contains authentication cookies (SAPISID, etc.)
Treat it like a password:
- Add browser.json to .gitignore
- Never commit or share browser.json
- Keep file permissions restricted (chmod 600 on Unix)
"""

# In-memory cache for search queries within a run
SEARCH_CACHE = {}

# Setup logging
def setup_logging(log_file='playlist_import.log'):
    """Configure logging to both file and console."""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates when reinitializing
    if logger.handlers:
        for h in list(logger.handlers):
            logger.removeHandler(h)

    # File handler
    fh = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    fh.setLevel(logging.INFO)
    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)

    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

# initialize default logger (can be reinitialized in main with a different file)
logger = setup_logging()

def retry_on_failure(max_attempts=3, backoff=2):
    """
    Retry decorator for network calls with exponential backoff.
    Retries on requests exceptions, timeouts, connection errors and HTTP 5xx responses.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Retry on requests network/connection/timeout errors
                    retryable = False
                    if isinstance(e, requests.exceptions.RequestException):
                        retryable = True
                    # If exception has 'response' with status_code, treat 5xx as retryable
                    resp = getattr(e, 'response', None)
                    if resp is not None and getattr(resp, 'status_code', 0) >= 500:
                        retryable = True

                    if not retryable or attempt == max_attempts:
                        # final attempt or non-retryable -> raise
                        raise

                    wait = backoff ** (attempt - 1)
                    logger.info(f"    Retry {attempt}/{max_attempts} after {wait}s... ({type(e).__name__})")
                    time.sleep(wait)
            return None
        return wrapper
    return decorator

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

def normalize_for_search(title, artist):
    """
    Normalize title and artist for better search results.
    Collapses whitespace and formats query for YouTube Music.
    """
    # Collapse whitespace
    title = ' '.join(title.split()) if title else ''
    artist = ' '.join(artist.split()) if artist else ''
    
    # Format: "Title" Artist for better matching
    if title and artist:
        return f'"{title}" {artist}'
    elif title:
        return f'"{title}"'
    elif artist:
        return artist
    return ''

@retry_on_failure()
def search_youtube_music(yt, title, artist):
    """
    Search YouTube Music for a song by title and artist.
    Uses an in-memory cache for the normalized query to avoid duplicate searches during a run.
    Attempts to pick a result that best matches title/artist before falling back to first result.
    """
    try:
        query = normalize_for_search(title, artist)
        if not query:
            return None

        # Cache lookup
        if query in SEARCH_CACHE:
            return SEARCH_CACHE[query]

        results = yt.search(query, filter='songs', limit=5)
        if not results:
            SEARCH_CACHE[query] = None
            return None

        # Try to prefer results that contain title or artist tokens (simple heuristic)
        norm_title = (title or '').casefold()
        norm_artist = (artist or '').casefold()
        best = None
        for r in results:
            r_title = (r.get('title') or '').casefold()
            r_artists = ' '.join((a.get('name') for a in r.get('artists', []) if a.get('name'))).casefold()
            if norm_title and norm_title in r_title:
                best = r
                break
            if norm_artist and norm_artist in r_artists:
                best = r
                break

        if not best:
            best = results[0]

        vid = best.get('videoId')
        SEARCH_CACHE[query] = vid
        return vid

    except Exception as e:
        logger.warning(f"    Search error for '{title}' by '{artist}': {e}")
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
            'description': playlist.get('description', ''),
            'songs': songs
        }
    except ImportError:
        logger.error("ERROR: spotipy library not installed!")
        logger.error("Install with: pip install spotipy")
        logger.error("Set environment variables: SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET")
        return None
    except Exception as e:
        logger.error(f"ERROR parsing Spotify playlist: {e}")
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
    
    logger.info(f"\nReading CSV file: {csv_file}")
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            
            # Validate CSV structure
            has_mediaid = 'MediaId' in headers
            has_playlistname = 'PlaylistName' in headers
            has_url = 'URL' in headers or 'url' in headers
            has_title = 'Title' in headers
            has_description = 'Description' in headers
            
            # Warn if missing essential columns
            if not has_mediaid and not has_title and not has_url:
                logger.warning("  ⚠ Warning: CSV missing Title, MediaId, or URL columns")
            
            # Determine playlist name
            if has_playlistname:
                default_playlist_name = None
            else:
                # Use filename as playlist name
                default_playlist_name = os.path.splitext(os.path.basename(csv_file))[0]
            
            for row_num, row in enumerate(reader, start=2):  # start=2 accounts for header row
                try:
                    # Get playlist name and normalize
                    if has_playlistname:
                        playlist_name = (row.get('PlaylistName') or '').strip()
                    else:
                        playlist_name = default_playlist_name
                    
                    if not playlist_name:
                        logger.warning(f"  ⚠ Row {row_num}: Skipping - no playlist name")
                        continue
                    
                    # Get description if provided
                    description = (row.get('Description') or '').strip() if has_description else ''
                    
                    # Get video ID (try multiple methods)
                    video_id = None
                    title = (row.get('Title') or '').strip()
                    artists = (row.get('Artists') or row.get('Artist') or '').strip()
                    
                    # Method 1: Direct MediaId/VideoId
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
                    
                    if not video_id and not title:
                        logger.warning(f"  ⚠ Row {row_num}: Skipping - no video ID or title")
                        continue
                    
                    if playlist_name not in playlists:
                        playlists[playlist_name] = {
                            'songs': [],
                            'description': description
                        }
                    
                    playlists[playlist_name]['songs'].append({
                        'videoId': video_id,
                        'title': title,
                        'artists': artists,
                        'search_needed': search_needed,
                        'row_num': row_num
                    })
                    
                except Exception as e:
                    logger.error(f"  ✗ Row {row_num}: Error parsing - {e}")
                    continue
        
        total_songs = sum(len(p['songs']) for p in playlists.values())
        logger.info(f"✓ Found {len(playlists)} playlist(s) with {total_songs} total songs")
        return playlists
    
    except Exception as e:
        logger.error(f"ERROR reading CSV: {e}")
        import traceback
        traceback.print_exc()
        return None

@retry_on_failure()
def add_songs_batch(yt, playlist_id, video_ids):
    """Add a batch of songs to a playlist with retry logic."""
    return yt.add_playlist_items(
        playlistId=playlist_id,
        videoIds=video_ids,
        duplicates=False
    )

def import_playlist(yt, playlist_name, playlist_data, append=True, privacy='PRIVATE'):
    """
    Import a single playlist to YouTube Music.
    If append=True and playlist exists, adds songs to existing playlist.
    If append=False, always creates a new playlist.
    """
    songs = playlist_data.get('songs', playlist_data) if isinstance(playlist_data, dict) else playlist_data
    description = playlist_data.get('description', '') if isinstance(playlist_data, dict) else ''
    
    logger.info(f"\n{'='*70}")
    logger.info(f"Processing: {playlist_name} ({len(songs)} songs)")
    logger.info('='*70)
    
    try:
        playlist_id = None
        
        # Check if playlist already exists (if append mode)
        if append:
            logger.info("  Checking for existing playlist...")
            try:
                existing_playlists = yt.get_library_playlists(limit=None)
                for pl in existing_playlists:
                    existing_title = (pl.get('title') or '').strip().casefold()
                    target_title = (playlist_name or '').strip().casefold()
                    if existing_title == target_title:
                        playlist_id = pl.get('playlistId')
                        logger.info(f"✓ Found existing playlist (ID: {playlist_id})")
                        logger.info(f"  Will append songs to existing playlist")
                        break
            except Exception as e:
                logger.warning(f"  Warning: Could not check for existing playlists: {e}")
        
        # Create new playlist if doesn't exist
        if not playlist_id:
            # Only add auto-description if no description provided
            if not description:
                description = f"" # I would rather it's blank than auto-generated
            
            playlist_id = yt.create_playlist(
                title=playlist_name,
                description=description,
                privacy_status=privacy
            )
            logger.info(f"✓ Created new playlist (ID: {playlist_id}, Privacy: {privacy})")
        
        successful = 0
        failed = 0
        searched = 0
        skipped = 0
        failed_songs = []
        
        # Batch processing
        batch = []
        batch_size = 20
        
        for i, song in enumerate(songs, 1):
            row_info = f" (Row {song.get('row_num')})" if song.get('row_num') else ""
            try:
                video_id = song['videoId']
                
                # If no video ID, search for it
                if not video_id and song.get('search_needed'):
                    logger.info(f"  Searching{row_info}: {song['title']} - {song['artists']}")
                    video_id = search_youtube_music(yt, song['title'], song['artists'])
                    searched += 1
                    
                    if not video_id:
                        raise Exception("Song not found in search")
                
                if not video_id:
                    raise Exception("No video ID available")
                
                # Add to batch
                batch.append(video_id)
                
                # Process batch when full or at end
                if len(batch) >= batch_size or i == len(songs):
                    try:
                        add_songs_batch(yt, playlist_id, batch)
                        successful += len(batch)
                        logger.info(f"  ✓ Added batch of {len(batch)} songs")
                        batch = []
                        time.sleep(1)  # Rate limiting between batches
                    except Exception as e:
                        error_msg = str(e)
                        # Check for success reported as error (ytmusicapi quirk)
                        if 'STATUS_SUCCEEDED' in error_msg:
                            successful += len(batch)
                        # Check if songs already in playlist
                        elif 'already' in error_msg.lower() or 'duplicate' in error_msg.lower():
                            skipped += len(batch)
                        else:
                            # Batch failed, log all songs in batch
                            for vid in batch:
                                failed += 1
                                matching_song = next((s for s in songs if s.get('videoId') == vid), None)
                                if matching_song:
                                    failed_songs.append({
                                        'row': matching_song.get('row_num', '?'),
                                        'title': matching_song['title'],
                                        'artists': matching_song['artists'],
                                        'error': error_msg
                                    })
                        batch = []
                
                # Progress indicator
                if i % 25 == 0 or i == len(songs):
                    status = f"  Progress: {i}/{len(songs)} songs"
                    if searched > 0:
                        status += f" ({searched} searched)"
                    logger.info(status)
                
            except Exception as e:
                error_msg = str(e)
                failed += 1
                failed_songs.append({
                    'row': song.get('row_num', '?'),
                    'title': song['title'],
                    'artists': song['artists'],
                    'error': error_msg
                })
                logger.warning(f"  ✗{row_info}: {song['title']} - {error_msg}")
        
        logger.info(f"\n✓ Completed '{playlist_name}'")
        logger.info(f"  ✓ Successfully added: {successful}/{len(songs)} songs")
        if searched > 0:
            logger.info(f"  🔍 Songs found by search: {searched}")
        if skipped > 0:
            logger.info(f"  ⏭ Skipped (already in playlist): {skipped}")
        if failed > 0:
            logger.error(f"  ✗ Failed: {failed} songs")
            logger.error(f"\nFailed songs:")
            for fs in failed_songs[:20]:
                logger.error(f"  - Row {fs['row']}: {fs['title']} by {fs['artists']}")
                logger.error(f"    Error: {fs['error']}")
            if len(failed_songs) > 20:
                logger.error(f"  ... and {len(failed_songs) - 20} more (see log file)")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ ERROR processing playlist '{playlist_name}': {e}")
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
  
  # Create public playlist
  python playlist_importer.py --public playlist.csv

AUTHENTICATION:
  First time setup: python playlist_importer.py --setup
  Or manually run: ytmusicapi browser
        '''
    )
    
    parser.add_argument('files', nargs='*', help='CSV file(s) to import')
    parser.add_argument('--setup', action='store_true', help='Run interactive authentication setup')
    parser.add_argument('--spotify', help='Import from Spotify playlist URL')
    parser.add_argument('--no-append', action='store_true', help='Always create new playlists instead of appending to existing ones')
    parser.add_argument('--public', action='store_true', help='Create public playlists (default is private)')
    parser.add_argument('--log', default='playlist_import.log', help='Log file path (default: playlist_import.log)')
    
    args = parser.parse_args()
    
    # Reinitialize logging with custom log file if specified
    global logger
    logger = setup_logging(args.log)
    
    # Determine settings
    append_mode = not args.no_append
    privacy = 'PUBLIC' if args.public else 'PRIVATE'
    
    # Handle setup mode
    if args.setup:
        if setup_authentication():
            logger.info("\n✓ Setup complete! You can now import playlists.")
        else:
            logger.error("\n✗ Setup failed. Please try again.")
        return
    
    # Check for authentication
    if not os.path.exists('browser.json'):
        logger.error("ERROR: browser.json not found!")
        logger.error("\nRun authentication setup first:")
        logger.error("  python playlist_importer.py --setup")
        logger.error("\nOr manually run: ytmusicapi browser")
        sys.exit(1)
    
    # Initialize YouTube Music client
    try:
        yt = YTMusic('browser.json')
        logger.info("✓ Successfully authenticated with YouTube Music")
    except Exception as e:
        logger.error(f"ERROR initializing YouTube Music: {e}")
        logger.error("\nTry running authentication setup again:")
        logger.error("  python playlist_importer.py --setup")
        sys.exit(1)
    
    # Handle Spotify import
    if args.spotify:
        logger.info(f"\nImporting from Spotify: {args.spotify}")
        playlist_data = parse_spotify_playlist(args.spotify)
        if playlist_data:
            import_playlist(yt, playlist_data['name'], playlist_data, append=append_mode, privacy=privacy)
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
        logger.error("ERROR: No CSV files found!")
        sys.exit(1)
    
    logger.info(f"\n{'='*70}")
    logger.info(f"Found {len(csv_files)} CSV file(s) to import")
    logger.info(f"Privacy: {privacy}, Append mode: {append_mode}")
    logger.info('='*70)
    for f in csv_files:
        logger.info(f"  - {f}")
    
    # Process each CSV file
    total_playlists = 0
    for i, csv_file in enumerate(csv_files, 1):
        logger.info(f"\n{'#'*70}")
        logger.info(f"# Processing file {i}/{len(csv_files)}: {os.path.basename(csv_file)}")
        logger.info(f"{'#'*70}")
        
        playlists = import_playlist_from_csv(yt, csv_file)
        if playlists:
            for playlist_name, playlist_data in playlists.items():
                if import_playlist(yt, playlist_name, playlist_data, append=append_mode, privacy=privacy):
                    total_playlists += 1
    
    logger.info("\n" + "="*70)
    logger.info(f"ALL COMPLETE - Imported {total_playlists} playlists from {len(csv_files)} file(s)")
    logger.info(f"Detailed log saved to: {args.log}")
    logger.info("="*70)

if __name__ == "__main__":
    main()