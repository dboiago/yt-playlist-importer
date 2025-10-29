import csv
import json
import os
import sys
import time
import re
from ytmusicapi import YTMusic

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
    print("7. Right-click → Copy → Copy as cURL (bash)")
    print("\nPaste the cURL command below (it will be very long):")
    print("(Press Enter twice when done)\n")
    
    lines = []
    while True:
        line = input()
        if not line and lines:
            break
        lines.append(line)
    
    curl_command = ' '.join(lines)
    
    # Parse headers from cURL command
    headers = {}
    
    # Extract User-Agent
    ua_match = re.search(r"-H '([Uu]ser-[Aa]gent: [^']+)'", curl_command)
    if ua_match:
        headers['User-Agent'] = ua_match.group(1).split(': ', 1)[1]
    
    # Extract Cookie
    cookie_match = re.search(r"-H '([Cc]ookie: [^']+)'", curl_command)
    if cookie_match:
        headers['Cookie'] = cookie_match.group(1).split(': ', 1)[1]
    
    # Extract X-Goog-AuthUser
    auth_match = re.search(r"-H '(X-Goog-AuthUser: [^']+)'", curl_command)
    if auth_match:
        headers['X-Goog-AuthUser'] = auth_match.group(1).split(': ', 1)[1]
    
    if not headers.get('Cookie') or 'SAPISID' not in headers['Cookie']:
        print("\n❌ ERROR: Could not parse headers correctly!")
        print("Make sure you copied the full cURL command.")
        return False
    
    # Save to browser.json
    with open('browser.json', 'w') as f:
        json.dump(headers, f, indent=2)
    
    print("\n✓ Authentication saved to browser.json")
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
            headers = reader.fieldnames
            
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
                
                # Method 1: Direct MediaId/VideoId
                if has_mediaid:
                    video_id = row['MediaId'].strip()
                elif 'VideoId' in headers:
                    video_id = row['VideoId'].strip()
                
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

def import_playlist(yt, playlist_name, songs):
    """
    Import a single playlist to YouTube Music.
    """
    print(f"\n{'='*70}")
    print(f"Processing: {playlist_name} ({len(songs)} songs)")
    print('='*70)
    
    try:
        # Create the playlist
        playlist_id = yt.create_playlist(
            title=playlist_name,
            description=f"Imported playlist - {len(songs)} songs"
        )
        print(f"✓ Created playlist (ID: {playlist_id})")
        
        successful = 0
        failed = 0
        searched = 0
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
                failed += 1
                
                # Check for success reported as error (ytmusicapi quirk)
                if 'STATUS_SUCCEEDED' in error_msg:
                    successful += 1
                    failed -= 1
                else:
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
        print(f"✗ ERROR creating playlist '{playlist_name}': {e}")
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
    
    args = parser.parse_args()
    
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
            import_playlist(yt, playlist_data['name'], playlist_data['songs'])
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
                if import_playlist(yt, playlist_name, songs):
                    total_playlists += 1
    
    print("\n" + "="*70)
    print(f"ALL COMPLETE - Imported {total_playlists} playlists from {len(csv_files)} file(s)")
    print("="*70)

if __name__ == "__main__":
    main()