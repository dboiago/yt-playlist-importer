# YouTube Music Playlist Importer

A Python tool for importing playlists to YouTube Music from CSV files, Spotify playlists, and other sources.

Main script: `playlist_importer.py`

## Features
- Multiple CSV formats supported: Kreate exports, simple Title/Artist CSVs, URL lists
- Spotify import: Import directly from Spotify playlist URLs (requires setup)
- Smart fallback: Searches YouTube Music if video IDs not provided
- Playlist appending: Automatically appends to existing playlists (configurable)
- Batch processing: Efficiently adds songs in batches
- Retry logic: Exponential backoff for transient failures
- Progress tracking: Real-time feedback on import status

## Prerequisites
- Python 3.x
- Install dependencies:
  - ytmusicapi: 
  ```bash
  pip install ytmusicapi
  ```
  - Optional (Spotify):
  ```bash
  pip install spotipy
  ```
- Authentication:
  - Run interactive setup in the script: 
  ```bash
  python playlist_importer.py --setup
  ```
  - Or run: 
  ```bash
  ytmusicapi browser
  ``` 
  to generate headers and save them as `browser.json`.

## Installation
1. Clone the repository
    ```bash
    git clone https://github.com/yourusername/yt-music-importer.git
    cd yt-music-importer
    ```

2. Install dependencies
    ```bash
    pip install ytmusicapi
    ```

3. Optional: For Spotify support
    ```bash
    pip install spotipy
    ```

## Authentication
1. Run the interactive setup to authenticate with YouTube Music:
    ```bash
    python playlist_importer.py --setup
    ```
2. Follow the prompts to copy your browser's request headers. This creates browser.json which contains your authentication cookies.

⚠️ SECURITY WARNING: browser.json contains sensitive authentication data. Never commit or share this file!

## Manual Authentication (Alternative)
    ytmusicapi browser
This creates browser.json in the current directory.

## How to get auth headers
1. Open Developer Tools and go to the Network tab
    Open the developer tools in your browser and go to the network tab. You can do this by right-clicking anywhere on the page and selecting 'Inspect' or by pressing 'Ctrl + Shift + I'.
2. Sign into YouTube Music
    Go to music.youtube.com and make sure you are signed in with your Google account.
3. Find an authenticated POST request
    Filter by /browse in the search bar of the Network tab. Find a POST request with a status of 200

    Firefox (recommended):
        Verify that the request looks like this: Status : 200, Method : POST, Domain : music.youtube.com, File : browse?...
        Copy the request headers (right click > copy > copy request headers)

    ```text
    | [] | {} /browse     x | ||  +  o  o  | All HTML CSS JS XHR Fonts Images Media WS Other | [✓] Disable Cache |
    --------------------------------------------------------------------------------------------------------------
    | Status | Method | Domain           | File                     | Initiator | Type | Thransfered | Size      |
    --------------------------------------------------------------------------------------------------------------
    |   200  | POST   | music.youtbe.com | browse?prettyPrint=fales | fetch     | json | 16.74 kB    | 246.48 kB |
    ```

    Chromium based (Chrome/Edge):
        Verify that the request looks like this: Status : 200, Name : browse?...
        Click on the Name of any matching request. In the “Headers” tab, scroll to the section “Request headers” and copy everything starting from “accept: */*” to the end of the section

## Usage
- Import a single CSV:
  - `python playlist_importer.py playlist.csv`
- Import many files (globs or directory):
  - `python playlist_importer.py *.csv`
  - `python playlist_importer.py path\to\csv\folder`
- Import from Spotify:
  - `python playlist_importer.py --spotify https://open.spotify.com/playlist/...`
- Interactive auth setup:
  - `python playlist_importer.py --setup`
  - `(Paste headers, press Ctrl+D(Unix)/Ctrl+Z(Windows) when done)`
- Import and create new playlists:
  - `python playlist_importer.py --no-append *.csv`

## Import from Spotify
- Requires SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET environment variables
    ```text
    export SPOTIPY_CLIENT_ID='your_client_id'
    export SPOTIPY_CLIENT_SECRET='your_client_secret'
    python playlist_importer.py --spotify "https://open.spotify.com/playlist/..."
    ```

## CSV Formats
The importer supports multiple CSV formats:
 - Kreate Format (Full)
    ```text
    PlaylistBrowseId,PlaylistName,MediaId,Title,Artists,Duration,ThumbnailUrl
    ,My Playlist,dQw4w9WgXcQ,Song Title,Artist Name,180,https://...
    ```
- Simple Format
    ```text
    Title,Artist
    Song Title,Artist Name
    Another Song,Another Artist
    ```
- URL Format
    ```text
    URL
    https://music.youtube.com/watch?v=dQw4w9WgXcQ
    https://www.youtube.com/watch?v=dQw4w9WgXcQ
    ```

## Command-Line Options
```text
usage: playlist_importer.py [-h] [--setup] [--spotify SPOTIFY] [--no-append] [files ...]

positional arguments:
  files                CSV file(s) to import

optional arguments:
  -h, --help           show this help message and exit
  --setup              Run interactive authentication setup
  --spotify SPOTIFY    Import from Spotify playlist URL
  --no-append          Always create new playlists instead of appending
```

## Behavior notes & troubleshooting
- Authentication Issues
  If you get authentication errors:

  1. Delete browser.json
  2. Run python playlist_importer.py --setup again
  3. Make sure you're logged into YouTube Music in your browser
  4. Copy the entire request headers (should be very long)

- "Song not found" Errors
  Some songs may not be available on YouTube Music:

  - Regional restrictions
  - Deleted/removed videos
  - Incorrect song titles in CSV

Check the log output for specific errors.

- Rate Limiting
  If you hit rate limits:

  - The script includes built-in delays (0.3s between songs, 1s between batches)
  - Retry logic handles temporary rate limits
  - For very large imports, consider splitting into smaller batches

- Security Best Practices
  1. Never commit browser.json - It's in .gitignore by default
  2. Don't share browser.json - It contains your authentication cookies
  3. Set restrictive permissions: chmod 600 browser.json (Unix/Linux)
  4. Regenerate regularly: Re-run setup if you suspect compromise

- Known Limitations
  - Spotify import requires API credentials (free but requires registration)
  - Search fallback may occasionally match wrong songs for ambiguous titles
  - YouTube Music API has rate limits (handled with retry logic)
  - Some songs may not be available due to regional restrictions

## Contributing
- Contributions welcome! Please:
  1. Fork the repository
  2. Create a feature branch
  3. Add tests if applicable
  4. Submit a pull request

## License
This project is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0).  
You are free to use and modify the code for non-commercial purposes, but you must give attribution and distribute any derivative works under the same license. See LICENSE for details.

## Acknowledgments
  - Built with ytmusicapi
  - Spotify support via spotipy