spodsync 
Download Spotify tracks, albums and playlists, and get synced lyrics for all of them, with one command. 
License: MIT Python 3.9+ 
spodsync-launch "https://open.spotify.com/playlist/xxxxxxxx" --in-place
 Unofficial project. Not affiliated with or endorsed by Spotify. Use it only for content you own or are otherwise
permitted to download. See Sunnify’s legal disclaimer, which applies here too. 
 Contents 
What it does
Requirements
Install
Quick start
Usage
Options
How it works
Troubleshooting
Known limitations
License 
What it does 
spodsync chains two tools together: 
Sunnify downloads the audio as MP3s with real ID3 tags (title, artist, album, year, track number) and cover art. spodsync
runs Sunnify’s headless CLI (sunnify download <url>) for you.
spodsync then fetches matching synced lyrics from lrclib.net, a free and open lyrics database, and saves each one as a
.lrc file right next to its .mp3. 
You can also skip the download step entirely and just add lyrics to MP3s you already have. 
Requirements 
Python 3.9+
Sunnify, installed and on your PATH as sunnify. This is only needed if you pass a Spotify URL. Install it with their one-line
installer, the Homebrew cask, or: 
pipx install git+https://github.com/sunnypatell/sunnify-spotify-downloader
 Then check that it works with sunnify doctor.
mutagen and requests (installed automatically). 
spodsync does not install or configure Sunnify for you. 
Install 
Arch Linux (one-shot) 
This installs everything, Sunnify included, in one paste. It works in bash, zsh and fish. 
sudo pacman -S --needed --noconfirm python-pipx git \
&& pipx ensurepath \
&& pipx install git+https://github.com/sunnypatell/sunnify-spotify-downloader \
&& pipx install git+https://github.com/CHEESEGRATER45/spodsync
 Then open a new terminal (so ~/.local/bin is on your PATH) and check that everything works: 
sunnify doctorspodsync-launch To update later: 
--version
pipx upgrade sunnify-spotify-downloader
pipx upgrade spodsync

Other systems (from source) 
git clone https://github.com/CHEESEGRATER45/spodsync.git
cd spodsync
pip install .
 This installs the spodsync-launch command. For development, use an editable install: 
pip install -e .

Quick start 
Pick one of the two modes. 
--in-place (recommended) 
Works directly on the folder where Sunnify saves your library (auto-detected, usually ~/Music/Sunnify). There is no separate
folder, no copying and no duplication. 
spodsync-launch "https://open.spotify.com/playlist/xxxxxxxx" --in-place

--dir <project> (separate, curated copy) 
Keeps a second copy of your library under <project>/music/. Files are hard-linked to Sunnify’s originals where possible, so
this costs no extra disk space on the same filesystem. Where hard links aren’t possible (for example across drives), the files are
copied instead. This is useful when you want a specific subset of your library, such as for an MP3 player or phone. 
spodsync-launch "https://open.spotify.com/playlist/xxxxxxxx" --dir ~/projects/my-player-sync
 With either mode, running with no URL just re-scans for missing lyrics. That is handy if you already have MP3s and only want lyrics
for them. 
Usage 
By default, spodsync works from the current folder. Spotify links go to Sunnify, the audio lands in music/, and then spodsync
fetches lyrics for everything in there. 
my-project/
└── music/ <- Sunnify downloads into here; spodsync scans it after
 cd my-project
 # Download a playlist/album/track, then fetch lyrics for it
spodsync-launch "https://open.spotify.com/playlist/xxxxxxxx"
 # Multiple links in one run
spodsync-launch "https://open.spotify.com/album/aaa" "https://open.spotify.com/track/bbb"
 # No link: just (re-)scan music/ for missing lyrics
spodsync-launch
 # Point at a different project folderspodsync-launch "https://open.spotify.com/track/abc" --dir ~/Music/my-collection
 # Re-fetch lyrics even where a .lrc already exists
spodsync-launch --force

Passing extra flags to Sunnify 
Anything after a literal -- is forwarded to sunnify download for each URL: 
spodsync-launch "https://open.spotify.com/track/abc" -- --format mp3
 Sunnify’s flag names can change between versions, so run sunnify download --help to see what your installed version
supports. 
Make sure Sunnify outputs MP3s. spodsync only reads .mp3 files. M4A, FLAC, Opus and WAV output will not be
picked up. 
OptionsFlag DescriptionSPOTIFY_URL ... Zero or more Spotify links/URIs to download via Sunnify first.--in-place Work directly on Sunnify’s own save folder, with no separate copy. Ignores --dir.--dir PATH Project folder for a separate, curated copy under <dir>/music/ (hard-linked or copied from Sunnify’s
originals). Defaults to the current directory. Ignored if --in-place is given.--force Re-fetch lyrics even if a .lrc file already exists (overwrites it).--skip-download Only run the lyrics step, even if URLs are given.-- ARGS... Everything after -- is passed through to sunnify download.--version Print the version and exit.
How it works 
Download (optional, once per URL). Runs sunnify downloadcodes follow Sunnify’s own contract: 
<url> as a subprocess and streams its output live. Exit
0: ok
1: partial (some tracks skipped or failed; the run continues)
2 / 3: usage or environment error (reported; the run continues to the next URL) 
If sunnify isn’t on your PATH, you get an install pointer instead of a crash.
Lyrics. Recursively finds every .mp3 under <dir>/music/, skipping any that already have a same-named .lrc unless -
force is passed, so there is no duplicate work and no wasted API calls. For the rest, it reads the TIT2 / TPE1 / TALB ID3
frames and the duration with mutagen, then queries lrclib.net. It tries the exact-match /api/get endpoint first and falls
back to the fuzzy /api/search endpoint. 
Tracks with missing or unreadable tags, or with no lyrics on lrclib.net, are reported and skipped. spodsync keeps going and prints
a summary at the end. 
If a track has no usable ID3 tags but its filename looks like Title - Artist.mp3 (including a trailing [spotify-id] suffix that
some downloaders add), spodsync parses the filename instead. Those tracks are marked (matched via filename, no ID3
tags) in the output. 
Troubleshooting 
Downloads seem to disappear. spodsync finds Sunnify’s save folder by parsing a line Sunnify prints. Check ~/Music/Sunnify,
or wherever sunnify doctor says your library is configured, and look there manually. 
Some tracks failed with HTTP 503. lrclib.net can rate-limit large syncs. spodsync retries automatically, but a track can still fail. Re
run spodsync-launch with no URL (so nothing is re-downloaded) and it will retry only what’s missing. 
No lyrics for some songs. Not every track has lyrics on lrclib.net. Those tracks are listed in the end-of-run summary. 
Nothing is being picked up. Check that your files are .mp3 and not another format. See the note under Passing extra flags to
Sunnify.sunnify not found. Install Sunnify (see Requirements) and confirm sunnify doctor runs cleanly. 
Known limitations 
MP3 only. spodsync scans for .mp3 specifically and reads tags via mutagen.mp3.MP3.
Depends on Sunnify’s console output format. The save location is detected by parsing a line of the form » <url><path> [<format>]. If a future Sunnify version changes that wording, detection could silently stop working.
lrclib.net rate limits. Large playlists can trigger occasional HTTP 503 responses (see Troubleshooting).
Sunnify must be installed and working first. spodsync doesn’t install or configure it for you. 
->
License 
MIT. See LICENSE
