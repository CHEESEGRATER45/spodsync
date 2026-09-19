# spodsync

> **Unofficial project.** Not affiliated with or endorsed by Spotify. Use it
> for content you own or are otherwise permitted to download — see
> [Sunnify's own disclaimer](https://github.com/sunnypatell/sunnify-spotify-downloader#legal-disclaimer),
> which applies here too.

One command that downloads Spotify tracks/albums/playlists and fetches
matching synced lyrics for them:

```bash
spodsync-launch "https://open.spotify.com/playlist/xxxxxxxx"
```

Under the hood this chains two tools together:

1. **[Sunnify](https://github.com/sunnypatell/sunnify-spotify-downloader)** —
   downloads the audio as MP3s with real ID3 tags (title, artist, album,
   year, track number) and cover art. spodsync shells out to Sunnify's own
   headless CLI (`sunnify download <url>`) to do this.
2. **spodsync itself** — fetches matching synced lyrics from
   [lrclib.net](https://lrclib.net) (a free, open lyrics database) for
   whatever Sunnify downloaded, saving each as a `.lrc` file next to its
   `.mp3`.

## Two ways to run it

**`--in-place` (recommended for most people):** spodsync works directly on
wherever Sunnify actually saves your library (auto-detected — usually
`~/Music/Sunnify`). No separate folder, no copying, no duplication. This is
the simplest option if you just want your Sunnify library to have lyrics
alongside it.

```bash
spodsync-launch "https://open.spotify.com/playlist/xxxxxxxx" --in-place
```

**`--dir <project>` (for a separate, curated copy):** spodsync keeps a
second copy of your library under `<project>/music/`, hard-linked to
Sunnify's originals where possible (so it costs no extra disk space on the
same filesystem) or copied where it isn't (e.g. across drives). Useful if
you want a specific subset of your library — say, for copying onto an MP3
player or phone — separate from everything else Sunnify has ever
downloaded.

```bash
spodsync-launch "https://open.spotify.com/playlist/xxxxxxxx" --dir ~/projects/my-player-sync
```

Run either mode with no URL and it just (re-)scans for missing lyrics —
handy if you already have MP3s somewhere and only want lyrics for them.

## Requirements

- Python 3.9+
- **[Sunnify](https://github.com/sunnypatell/sunnify-spotify-downloader)**,
  installed and on your `PATH` as `sunnify` — only needed if you pass a
  Spotify URL. Install via their one-line installer, Homebrew cask, or
  `pipx install git+https://github.com/sunnypatell/sunnify-spotify-downloader`.
  Check it's working with `sunnify doctor`.
- [mutagen](https://pypi.org/project/mutagen/) and
  [requests](https://pypi.org/project/requests/) — installed automatically.

Sunnify's own terms (see its
[legal disclaimer](https://github.com/sunnypatell/sunnify-spotify-downloader#legal-disclaimer))
are for personal use on content you own or are permitted to download — that
applies here too.

## Install

```bash
git clone <your-repo-url>
cd spodsync
pip install .
```

This installs the `spodsync-launch` command. For local development:

```bash
pip install -e .
```

## Usage

Run it from a project folder. Spotify links go straight to Sunnify; audio
lands in `music/`, then spodsync fetches lyrics for everything in there.

```
my-project/
└── music/          <- Sunnify downloads into here; spodsync scans it after
```

```bash
cd my-project

# Download a playlist/album/track, then fetch lyrics for it
spodsync-launch "https://open.spotify.com/playlist/xxxxxxxx"

# Multiple links in one run
spodsync-launch "https://open.spotify.com/album/aaa" "https://open.spotify.com/track/bbb"

# No link — just (re-)scan music/ for missing lyrics
spodsync-launch

# Point at a different project folder
spodsync-launch "https://open.spotify.com/track/abc" --dir ~/Music/my-collection

# Re-fetch lyrics even where a .lrc already exists
spodsync-launch --force
```

### Passing extra flags to Sunnify

Anything after a literal `--` is forwarded straight to `sunnify download`
for each URL, e.g.:

```bash
spodsync-launch "https://open.spotify.com/track/abc" -- --format mp3
```

Sunnify's exact flag names can change between versions — run
`sunnify download --help` to see what your installed version supports.
**Make sure Sunnify is configured (or told, via `--`) to output MP3s** —
spodsync only reads `.mp3` files, so M4A/FLAC/Opus/WAV output won't be
picked up.

### Options

| Flag | Description |
|---|---|
| `SPOTIFY_URL ...` | Zero or more Spotify links/URIs to download via Sunnify first. |
| `--in-place` | Work directly on Sunnify's own save folder — no separate copy, no duplication. Ignores `--dir`. |
| `--dir PATH` | Project folder for a separate, curated copy under `<dir>/music/` (hard-linked/copied from Sunnify's originals). Defaults to the current directory. Ignored if `--in-place` is given. |
| `--force` | Re-fetch lyrics even if a `.lrc` file already exists (overwrites it). |
| `--skip-download` | Only run the lyrics step, even if URLs are given. |
| `-- ARGS...` | Everything after `--` is passed through to `sunnify download`. |
| `--version` | Print the version and exit. |

## How it works

1. **Download (optional, one per URL given):** runs
   `sunnify download <url>` as a subprocess and streams its output live.
   Exit codes follow Sunnify's own contract — `0` ok, `1` partial (some
   tracks skipped/failed, run continues), `2`/`3` usage/environment error
   (reported, run continues to the next URL). If `sunnify` isn't found on
   your `PATH`, you get an install pointer instead of a crash.
2. **Lyrics (always, unless `--skip-download` with no music):** recursively
   finds every `.mp3` under `<dir>/music/`, skipping ones that already have
   a same-named `.lrc` unless `--force` is passed — no duplicate work, no
   wasted API calls. For the rest, reads the `TIT2`/`TPE1`/`TALB` ID3
   frames and duration via [mutagen](https://mutagen.readthedocs.io/), then
   queries lrclib.net: the exact-match `/api/get` endpoint first, falling
   back to the fuzzy `/api/search` endpoint.

Tracks with missing/unreadable tags, or with no lyrics available on
lrclib.net, are reported and skipped — the tool keeps going and prints a
summary at the end. If a track has no usable ID3 tags but its filename
looks like `Title - Artist.mp3` (including a trailing `[spotify-id]`
suffix some downloaders add), spodsync falls back to parsing the filename
instead of skipping it — you'll see `(matched via filename, no ID3 tags)`
next to those in the output.

## Known limitations

- **MP3 only.** spodsync scans for `.mp3` specifically and reads tags via
  `mutagen.mp3.MP3`. If Sunnify is configured for M4A/FLAC/Opus/WAV, those
  files won't be picked up.
- **Depends on Sunnify's console output format.** spodsync figures out
  where Sunnify actually saved files by parsing a line it prints
  (`» <url>  ->  <path>  [<format>]`). If a future Sunnify version changes
  that wording, detection could silently stop working — if downloads seem
  to disappear, check `~/Music/Sunnify` (or wherever `sunnify doctor`
  reports as configured) manually.
- **lrclib.net rate limits.** Syncing a large playlist in one go can trip
  occasional `HTTP 503` responses under load. spodsync retries a few times
  automatically, but a track can still end up genuinely failing — just
  re-run spodsync-launch (with no URL, to skip re-downloading) and it'll
  retry only what's missing.
- **Sunnify must be installed and working first.** Run `sunnify doctor`
  before wiring it into spodsync; spodsync doesn't install or configure
  Sunnify for you.

## License

MIT — see [LICENSE](LICENSE).
