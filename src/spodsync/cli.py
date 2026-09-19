"""spodsync-launch: download tracks with Sunnify's CLI and/or fetch matching
synced lyrics (.lrc) from lrclib.net for every .mp3 in a music/ folder.

Two things can happen in one run, in this order:
  1. For every Spotify URL passed on the command line, shell out to Sunnify's
     own headless CLI (`sunnify download <url>`) to fetch the audio.
  2. Scan the project's music/ folder and fetch a matching .lrc for any .mp3
     that doesn't already have one (or all of them, with --force).

Run with no URLs and it just does step 2, exactly like before.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .lrclib import LrcLibError, get_synced_lyrics
from .tags import TagReadError, read_track_info

SUNNIFY_INSTALL_HINT = (
    "Install it from https://github.com/sunnypatell/sunnify-spotify-downloader "
    "(a one-line installer, Homebrew cask, or pipx are all documented there) "
    "and make sure the `sunnify` command is on your PATH."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spodsync-launch",
        description=(
            "Download tracks from Spotify links via Sunnify, then scan a "
            "music/ folder and fetch matching synced lyrics (.lrc) from "
            "lrclib.net. Pass no URLs to just do the lyrics step."
        ),
    )
    parser.add_argument(
        "urls",
        nargs="*",
        metavar="SPOTIFY_URL",
        help=(
            "Zero or more Spotify track/album/playlist links (or URIs) to "
            "download via Sunnify before the lyrics step runs."
        ),
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path.cwd(),
        help=(
            "Project folder containing the music/ subfolder to download "
            "into and scan (default: current directory). Ignored if "
            "--in-place is given."
        ),
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help=(
            "Skip the project music/ folder entirely and work directly on "
            "wherever Sunnify actually saves files (auto-detected). No "
            "copying, no hard-linking, no duplication — simplest option if "
            "you don't need a separate curated copy of your library."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch lyrics even if a .lrc file already exists for a track.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Only run the lyrics step, even if URLs are given (mainly for testing).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"spodsync {__version__}",
    )
    parser.epilog = (
        "Everything after a literal `--` is passed straight through to "
        "`sunnify download` for each URL (e.g. `spodsync-launch <url> -- "
        "--format mp3 --quality 320` if your Sunnify version supports those "
        "flags — run `sunnify download --help` to check)."
    )
    return parser


def split_passthrough_args(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split argv on the first literal `--`.

    Everything before it is spodsync-launch's own arguments; everything
    after is passed straight through to `sunnify download` untouched. Doing
    this ourselves (instead of using argparse.REMAINDER on a second
    variable-length positional) avoids REMAINDER's tendency to swallow our
    own flags once a URL is present.
    """
    if "--" in argv:
        idx = argv.index("--")
        return argv[:idx], argv[idx + 1 :]
    return argv, []


# --- Step 1: download via Sunnify's own CLI --------------------------------

# Sunnify prints a routing line before it starts downloading, e.g.:
#   » https://open.spotify.com/playlist/xxxx  ->  /home/user/Music/Sunnify  [mp3]
# We parse this to find out where it's *actually* saving files, since
# Sunnify uses its own saved default location and does not respect a
# --dir passed to spodsync-launch.
_SUNNIFY_ROUTE_RE = re.compile(r"->\s*(.+?)\s*\[(\w+)\]\s*$")


def _link_or_copy(src: Path, dst: Path) -> str:
    """Hard-link src to dst if possible (same filesystem, zero extra disk
    space); fall back to a real copy if that's not possible (different
    filesystem, or a filesystem/OS that doesn't support hard links).

    Returns "linked" or "copied" for reporting.
    """
    try:
        os.link(src, dst)
        return "linked"
    except OSError:
        # Cross-device link (EXDEV), unsupported filesystem, etc. — fall
        # back to a normal copy.
        shutil.copy2(src, dst)
        return "copied"


def _copy_missing_files(actual_dest: Path, project_music_dir: Path) -> tuple[int, int]:
    """Link (or copy) every file under actual_dest that doesn't already
    exist (by relative path) under project_music_dir.

    Prefers a hard link over a real copy: same file data, two paths, zero
    extra disk space, and Sunnify's own copy in actual_dest is completely
    unaffected either way — so its resume/dedup bookkeeping keeps working
    whether we end up hard-linking or falling back to a copy.

    It's also a full sync rather than "just what's new this run", so it
    self-heals any backlog left behind by earlier runs (e.g. tracks Sunnify
    resumed/skipped because it already had them from a prior session, which
    never made it into the project folder). Returns (linked_count, copied_count).
    """
    if actual_dest.resolve() == project_music_dir.resolve():
        return 0, 0
    if not actual_dest.is_dir():
        return 0, 0

    linked = 0
    copied = 0
    for src in actual_dest.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(actual_dest)
        dst = project_music_dir / rel
        if dst.exists():
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            result = _link_or_copy(src, dst)
            if result == "linked":
                linked += 1
            else:
                copied += 1
        except OSError as exc:
            print(f"warning: could not link/copy {src} -> {dst}: {exc}", file=sys.stderr)

    return linked, copied


def _sync_from_sunnify_dest(actual_dest: Path, project_music_dir: Path) -> None:
    project_music_dir.mkdir(parents=True, exist_ok=True)
    linked, copied = _copy_missing_files(actual_dest, project_music_dir)
    total = linked + copied
    if not total:
        return
    print(f"\nSunnify saves to {actual_dest}, not {project_music_dir} — brought {total} file(s) across", end="")
    if linked and copied:
        print(f" ({linked} hard-linked, {copied} copied — different filesystems).")
    elif linked:
        print(" (hard-linked, so this used no extra disk space).")
    else:
        print(" (copied — hard links aren't available between these folders).")
    print("Sunnify's own copy is left in place so its resume/dedup tracking keeps working.")


def download_with_sunnify(
    url: str, project_music_dir: Path | None, extra_args: list[str]
) -> tuple[int, Path | None]:
    """Run `sunnify download <url>`, stream its output live, and (unless
    project_music_dir is None, i.e. --in-place mode) sync whatever it
    downloads into project_music_dir if Sunnify saved it somewhere else
    (which it does by default — see _SUNNIFY_ROUTE_RE above).

    Returns (exit_code, detected_destination). exit_code follows Sunnify's
    documented contract: 0 ok, 1 partial success, 2 usage error, 3
    environment error. detected_destination is Sunnify's actual save
    location if we managed to parse it from its output, else None.
    """
    sunnify_path = shutil.which("sunnify")
    if not sunnify_path:
        print(
            "error: the `sunnify` command was not found on your PATH.\n"
            f"{SUNNIFY_INSTALL_HINT}",
            file=sys.stderr,
        )
        return 3, None

    if project_music_dir is not None:
        project_music_dir.mkdir(parents=True, exist_ok=True)

    command = [sunnify_path, "download", url, *extra_args]
    print(f"$ {' '.join(command)}")

    actual_dest: Path | None = None

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        print(f"error: failed to run sunnify: {exc}", file=sys.stderr)
        return 3, None

    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="")
        if actual_dest is None:
            match = _SUNNIFY_ROUTE_RE.search(line.strip())
            if match:
                actual_dest = Path(match.group(1)).expanduser()

    returncode = process.wait()

    if actual_dest is not None:
        if project_music_dir is not None:
            _sync_from_sunnify_dest(actual_dest, project_music_dir)
        # else: --in-place mode — nothing to sync, caller uses actual_dest directly.
    else:
        print(
            "warning: could not detect Sunnify's save location from its output; "
            "if downloaded files don't show up, check ~/Music/Sunnify manually.",
            file=sys.stderr,
        )

    return returncode, actual_dest


# --- Step 2: scan for lyrics (unchanged logic) ------------------------------


def find_mp3s(music_dir: Path) -> list[Path]:
    return sorted(music_dir.rglob("*.mp3"))


def process_file(mp3_path: Path, force: bool) -> str:
    """Process one MP3 file. Returns a short status string for reporting."""
    lrc_path = mp3_path.with_suffix(".lrc")

    if lrc_path.exists() and not force:
        return "skip (exists)"

    try:
        info = read_track_info(mp3_path)
    except TagReadError as exc:
        return f"skip (tags: {exc})"

    try:
        synced_lyrics = get_synced_lyrics(
            track_name=info.title,
            artist_name=info.artist,
            album_name=info.album,
            duration=info.duration,
        )
    except LrcLibError as exc:
        return f"error ({exc})"

    if not synced_lyrics:
        return "not found"

    lrc_path.write_text(synced_lyrics, encoding="utf-8")
    suffix = " (matched via filename, no ID3 tags)" if info.source == "filename" else ""
    return f"saved -> {lrc_path.name}{suffix}"


def fetch_lyrics(music_dir: Path, force: bool) -> int:
    if not music_dir.is_dir():
        print(f"error: {music_dir} does not exist or is not a directory", file=sys.stderr)
        return 1

    mp3_files = find_mp3s(music_dir)
    if not mp3_files:
        print(f"No .mp3 files found in {music_dir}")
        return 0

    print(f"\nFound {len(mp3_files)} .mp3 file(s) in {music_dir}\n")

    counts = {"saved": 0, "skipped": 0, "not_found": 0, "error": 0}

    for mp3_path in mp3_files:
        rel = mp3_path.relative_to(music_dir)
        status = process_file(mp3_path, force)
        print(f"  {rel}: {status}")

        if status.startswith("saved"):
            counts["saved"] += 1
        elif status.startswith("skip"):
            counts["skipped"] += 1
        elif status.startswith("not found"):
            counts["not_found"] += 1
        elif status.startswith("error"):
            counts["error"] += 1

    print(
        "\nLyrics done. "
        f"{counts['saved']} saved, "
        f"{counts['skipped']} skipped, "
        f"{counts['not_found']} not found, "
        f"{counts['error']} errors."
    )
    return 0


# --- Orchestration -----------------------------------------------------------


_DEFAULT_SUNNIFY_DIR = Path("~/Music/Sunnify").expanduser()


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    own_args, extra_sunnify_args = split_passthrough_args(argv)

    parser = build_parser()
    args = parser.parse_args(own_args)

    project_music_dir: Path | None = None if args.in_place else (args.dir / "music")

    had_download_failure = False
    detected_dest: Path | None = None

    if args.urls and not args.skip_download:
        if args.in_place:
            print(f"Downloading {len(args.urls)} link(s) in place (Sunnify's own folder)\n")
        else:
            print(f"Downloading {len(args.urls)} link(s) into {project_music_dir}\n")

        for url in args.urls:
            code, dest = download_with_sunnify(url, project_music_dir, extra_sunnify_args)
            if dest is not None:
                detected_dest = dest
            if code == 0:
                continue
            if code == 1:
                print(f"warning: {url} finished with some tracks skipped/failed (partial)")
                continue
            print(f"error: sunnify exited with code {code} for {url}", file=sys.stderr)
            had_download_failure = True

    if args.in_place:
        if detected_dest is not None:
            music_dir = detected_dest
        else:
            music_dir = _DEFAULT_SUNNIFY_DIR
            print(
                f"note: --in-place given but Sunnify's destination wasn't detected "
                f"this run (e.g. no URL given) — falling back to {music_dir}. "
                "Pass --dir to point somewhere specific instead."
            )
    else:
        music_dir = project_music_dir

    lyrics_exit = fetch_lyrics(music_dir, args.force)

    if had_download_failure:
        return 1
    return lyrics_exit


if __name__ == "__main__":
    sys.exit(main())
