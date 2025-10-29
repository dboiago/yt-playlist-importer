# YouTube Music CSV Importer

This repository contains a small script to import CSV playlists into YouTube Music using headers authentication.

Script: [d:/Python/yt-music-importer/add.py](d:/Python/yt-music-importer/add.py)  
Main function: [`import_csv_playlist`](d:/Python/yt-music-importer/add.py)

## CSV format
The script expects a CSV with these headers:
- PlaylistBrowseId, PlaylistName, MediaId, Title, Artists, Duration, ThumbnailUrl  
Only `PlaylistName` and `MediaId` (YouTube video ID) are required for import.

## Prerequisites
1. Python 3.x
2. Install ytmusicapi:
    ```sh
    pip install ytmusicapi
3. Authenticate with browser headers:
    ytmusicapi browser

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
4. Paste the headers
    Follow the prompts from ytmusicapi

## Usage
Process a single CSV, multiple files, glob pattern, or a directory:
    python [add.py](http://_vscodecontentref_/0) Punk.csv
    python [add.py](http://_vscodecontentref_/1) *.csv
    python [add.py](http://_vscodecontentref_/2) /path/to/csvs/

## The script will:
- Read CSV(s) and group songs by playlist name
- Create playlists on YouTube Music
- Add songs by videoId (from MediaId) to the created playlists
- Print progress, summary, and report failed adds

## Notes & Troubleshooting
- The script uses headers auth (browser.json). If the file is missing it will prompt to run ytmusicapi browser.
- The script contains a short sleep between adds to reduce rate-limiting.
- If ytmusicapi reports odd errors like containing STATUS_SUCCEEDED, the script treats those as successes.
