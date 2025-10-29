# YouTube Music Playlist Importer

Small utility to import playlists into YouTube Music from CSV files or a Spotify playlist URL.  
Main script: `playlist_importer.py`

## Features
- Import one or more CSV files (file, glob, or directory).
- Create playlists on YouTube Music and add songs by videoId.
- Fallback search on YouTube Music when a videoId is not present.
- Optional Spotify → YouTube import (requires `spotipy` and Spotify API creds).
- Interactive authentication helper that generates `browser.json` from a copied cURL request.

## Prerequisites
- Python 3.x
- Install dependencies:
  - ytmusicapi: `pip install ytmusicapi`
  - Optional (Spotify): `pip install spotipy`
- Authentication:
  - Run interactive setup in the script: `python playlist_importer.py --setup`
  - Or run: `ytmusicapi browser` to generate headers and save them as `browser.json`.

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

    | [] | {} /browse     x | ||  +  o  o  | All HTML CSS JS XHR Fonts Images Media WS Other | [✓] Disable Cache |
    --------------------------------------------------------------------------------------------------------------
    | Status | Method | Domain           | File                     | Initiator | Type | Thransfered | Size      |
    --------------------------------------------------------------------------------------------------------------
    |   200  | POST   | music.youtbe.com | browse?prettyPrint=fales | fetch     | json | 16.74 kB    | 246.48 kB |


    Chromium based (Chrome/Edge):
        Verify that the request looks like this: Status : 200, Name : browse?...
        Click on the Name of any matching request. In the “Headers” tab, scroll to the section “Request headers” and copy everything starting from “accept: */*” to the end of the section

## CSV formats supported
- Kreate-ish CSV: `PlaylistBrowseId, PlaylistName, MediaId, Title, Artists, Duration, ThumbnailUrl`
  - `PlaylistName` and `MediaId` (YouTube video ID) are preferred.
- Simple CSV: `Title, Artist` (will search YouTube Music to find the videoId).
- URL column: `URL` or `url` — will extract a YouTube video ID from common URL patterns.

If no `PlaylistName` column exists, the CSV filename (without extension) is used as the playlist name.

Search fallback: when no videoId is available the script uses ytmusicapi search (first result). This can be less accurate for ambiguous titles.

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

## Behavior notes & troubleshooting
- The script expects `browser.json` in the working directory. If missing it exits with instructions to run `--setup` or `ytmusicapi browser`.
- The interactive `--setup` asks you to paste a cURL command copied from the browser DevTools and parses headers (User-Agent, Cookie, X-Goog-AuthUser). Ensure you copy the full cURL.
- The script includes a small sleep between adds to reduce rate limits; searching songs waits slightly longer.
- ytmusicapi sometimes returns errors that actually indicate success (e.g., responses containing `STATUS_SUCCEEDED`). The script treats that pattern as success for add operations.
- Spotify import requires `SPOTIPY_CLIENT_ID` and `SPOTIPY_CLIENT_SECRET` environment variables and the `spotipy` package.

## Limitations & suggestions
- Search matching is basic (first result). Consider adding fuzzy matching or more restrictive query formatting if mismatches occur.
- The cURL parsing in `--setup` expects the cURL copy in a specific format; if parsing fails, run `ytmusicapi browser` instead.
- Large playlists may hit rate limits; slow the loop sleep if you experience throttling.

## License
This project is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0).  
You are free to use and modify the code for non-commercial purposes, but you must give attribution and distribute any derivative works under the same license. See LICENSE for details.