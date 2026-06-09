"""Generate podcast show notes from a local audio file."""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CLAUDE_CODE_SYSTEM_PREFIX = "You are Claude Code, Anthropic's official CLI for Claude."


SHOWNOTES_SYSTEM_PROMPT = """You generate show notes for an episode of Expanding Beyond, a casual tech \
podcast hosted by Monica and Urban. The notes go on the Fireside feed and need to feel like a real \
episode write-up — light, conversational, a little self-deprecating — not a corporate summary.

Produce a single Markdown document with exactly these sections, in this order:

## Title suggestions
Three to five short, punchy episode titles in the show's style. Examples from past episodes:
- "The one where we talk about AI"
- "Keep your database close"
- "Everyone is sick"
- "Keep your friends close, but your enemies closer"
Titles should be conversational, often a single phrase, sometimes a play on a quote, joke, or \
running thread from the episode. No colons, no subtitles, no clickbait.

## Summary
One to three sentences. Written in first person ("we") or naming the hosts (Monica, Urban). \
Describe what they actually argued about, did, or noticed — not a generic abstract. Skip openings \
like "In this episode" or "The hosts discuss". Imagine you're texting a friend what the episode is \
about. Light and a bit wry; not dry, not corporate, not LinkedIn.

## Mentioned
A flat bulleted list of every concrete person, project, company, product, book, article, video, \
tool, or URL referenced in the episode. Use Markdown links where:
- the URL is spoken aloud or clearly implied in the transcript, or
- the item has an obvious canonical URL you are confident about (e.g. GitHub Copilot → \
https://github.com/features/copilot, Anthropic → https://www.anthropic.com, Claude Code → \
https://www.claude.com/product/claude-code, Mastodon → https://joinmastodon.org).

When you are not confident about a URL, list the item as plain text. Do not group by category — \
one flat list, ordered roughly by when they came up. Skip generic items that don't link to \
anything (e.g. "the internet", "programming").

## Quotable moments
One to four short, interesting quotes with timestamps. Prefer lines that are funny, opinionated, \
or memorable. Light cleanup of filler words ("you know", "kind of", "like") is fine; do not \
rewrite or paraphrase. Skip the section entirely if nothing genuinely stands out.

Rules:
- Use HH:MM:SS timestamps when the episode is over an hour long, MM:SS otherwise.
- Do not fabricate. Only include items actually present in the transcript.
- If you are not sure of a URL, omit the link rather than guess.
- Title suggestions can draw on the strongest quotable moments.
- Do not include hosts list, episode number, or duration — that lives on the feed already.
"""


OAUTH_BETA_HEADER = "oauth-2025-04-20"
TOKEN_CONFIG_PATH = Path.home() / ".config" / "podcast-shownotes" / "oauth-token"


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


@dataclass
class Segment:
    start: float
    text: str


@dataclass
class Credentials:
    """Either api_key (for direct API access) or oauth_token (from `claude setup-token`)."""
    api_key: str | None = None
    oauth_token: str | None = None

    @property
    def uses_oauth(self) -> bool:
        return self.oauth_token is not None


def transcribe_mlx(audio_path: Path, model: str) -> list[Segment]:
    import mlx_whisper

    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=model,
        word_timestamps=False,
    )
    return [
        Segment(start=float(s["start"]), text=s["text"].strip())
        for s in result["segments"]
    ]


def transcribe_faster(audio_path: Path, model: str) -> list[Segment]:
    from faster_whisper import WhisperModel

    whisper = WhisperModel(model, device="auto", compute_type="auto")
    segments, _info = whisper.transcribe(str(audio_path), vad_filter=True)
    return [Segment(start=float(s.start), text=s.text.strip()) for s in segments]


def render_transcript(segments: Iterable[Segment]) -> str:
    return "\n".join(f"[{format_timestamp(s.start)}] {s.text}" for s in segments)


def resolve_credentials(*, force_login: bool = False) -> Credentials:
    """Look up Anthropic credentials.

    Order:
      1. ``ANTHROPIC_API_KEY`` env var (traditional API key).
      2. ``ANTHROPIC_OAUTH_TOKEN`` env var.
      3. Cached OAuth token at ``~/.config/podcast-shownotes/oauth-token``.
      4. Bootstrap via ``claude setup-token``.
    """
    if not force_login:
        if api_key := os.environ.get("ANTHROPIC_API_KEY"):
            return Credentials(api_key=api_key)
        if oauth := os.environ.get("ANTHROPIC_OAUTH_TOKEN"):
            return Credentials(oauth_token=oauth)
        if TOKEN_CONFIG_PATH.exists():
            token = TOKEN_CONFIG_PATH.read_text().strip()
            if token:
                return Credentials(oauth_token=token)

    return Credentials(oauth_token=bootstrap_oauth_token())


def bootstrap_oauth_token() -> str:
    """Run ``claude setup-token`` and cache the resulting OAuth token."""
    if not _command_exists("claude"):
        raise RuntimeError(
            "claude CLI not found on PATH. Install Claude Code from "
            "https://docs.claude.com/en/docs/claude-code or set ANTHROPIC_API_KEY."
        )

    print(
        "No Anthropic credentials found.\n"
        "Launching `claude setup-token` — finish the browser flow, then paste the token below.\n",
        file=sys.stderr,
    )
    subprocess.run(["claude", "setup-token"], check=True)

    print(file=sys.stderr)
    token = input("Paste the OAuth token: ").strip()
    if not token:
        raise RuntimeError("No token provided.")

    TOKEN_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CONFIG_PATH.write_text(token + "\n")
    TOKEN_CONFIG_PATH.chmod(0o600)
    print(f"Token cached at {TOKEN_CONFIG_PATH}", file=sys.stderr)
    return token


def _command_exists(name: str) -> bool:
    from shutil import which
    return which(name) is not None


def make_client(creds: Credentials):
    from anthropic import Anthropic

    if creds.api_key:
        return Anthropic(api_key=creds.api_key)
    return Anthropic(
        auth_token=creds.oauth_token,
        default_headers={"anthropic-beta": OAUTH_BETA_HEADER},
    )


def build_system_blocks(creds: Credentials) -> list[dict]:
    """Prefix with the Claude Code marker when using an OAuth subscription token."""
    blocks: list[dict] = []
    if creds.uses_oauth:
        blocks.append(
            {
                "type": "text",
                "text": CLAUDE_CODE_SYSTEM_PREFIX,
                "cache_control": {"type": "ephemeral"},
            }
        )
    blocks.append(
        {
            "type": "text",
            "text": SHOWNOTES_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    )
    return blocks


def generate_notes(transcript: str, claude_model: str, creds: Credentials) -> str:
    client = make_client(creds)
    message = client.messages.create(
        model=claude_model,
        max_tokens=4096,
        system=build_system_blocks(creds),
        messages=[
            {
                "role": "user",
                "content": f"Transcript:\n\n{transcript}",
            }
        ],
    )
    parts = [block.text for block in message.content if getattr(block, "type", None) == "text"]
    return "".join(parts).strip() + "\n"


def default_whisper_model() -> str:
    if is_apple_silicon():
        return "mlx-community/whisper-large-v3-turbo"
    return "large-v3-turbo"


def transcribe(audio_path: Path, model: str) -> list[Segment]:
    if is_apple_silicon():
        return transcribe_mlx(audio_path, model)
    return transcribe_faster(audio_path, model)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="shownotes",
        description="Generate podcast show notes from a local audio file.",
    )
    parser.add_argument(
        "audio",
        type=Path,
        nargs="?",
        help="Path to audio file (mp3, wav, m4a, flac, ...). Omit when using --login.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Where to write outputs (default: current directory).",
    )
    parser.add_argument(
        "--whisper-model",
        default=None,
        help=(
            "Whisper model. On Apple Silicon: a HuggingFace repo id "
            "(default: mlx-community/whisper-large-v3-turbo). "
            "Elsewhere: a faster-whisper model name (default: large-v3-turbo)."
        ),
    )
    parser.add_argument(
        "--claude-model",
        default="claude-opus-4-7",
        help="Anthropic model id used to generate show notes (default: claude-opus-4-7).",
    )
    parser.add_argument(
        "--transcript-only",
        action="store_true",
        help="Stop after transcribing; do not call Claude.",
    )
    parser.add_argument(
        "--force-transcribe",
        action="store_true",
        help="Re-run Whisper even if a cached transcript exists for this audio file.",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Run `claude setup-token` to (re)generate the OAuth token, then exit.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    sys.exit(_run(argv))


def _run(argv: list[str] | None) -> int:
    args = parse_args(argv)

    if args.login:
        resolve_credentials(force_login=True)
        return 0

    if args.audio is None:
        print("error: audio file is required (or pass --login)", file=sys.stderr)
        return 2

    if not args.audio.exists():
        print(f"error: audio file not found: {args.audio}", file=sys.stderr)
        return 1

    creds: Credentials | None = None
    if not args.transcript_only:
        creds = resolve_credentials()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.audio.stem
    transcript_path = args.output_dir / f"{stem}.transcript.txt"

    if transcript_path.exists() and not args.force_transcribe:
        print(f"Using cached transcript: {transcript_path}", file=sys.stderr)
        transcript = transcript_path.read_text()
    else:
        whisper_model = args.whisper_model or default_whisper_model()
        print(f"Transcribing {args.audio} with {whisper_model}...", file=sys.stderr)
        segments = transcribe(args.audio, whisper_model)
        transcript = render_transcript(segments)
        transcript_path.write_text(transcript)
        print(f"Wrote transcript: {transcript_path}", file=sys.stderr)

    if args.transcript_only:
        return 0

    assert creds is not None
    print(f"Generating show notes with {args.claude_model}...", file=sys.stderr)
    notes = generate_notes(transcript, args.claude_model, creds)

    notes_path = args.output_dir / f"{stem}.shownotes.md"
    notes_path.write_text(notes)
    print(f"Wrote show notes: {notes_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    main()
