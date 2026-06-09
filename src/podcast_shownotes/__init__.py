"""Generate podcast show notes from a local audio file."""

from __future__ import annotations

import argparse
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SHOWNOTES_SYSTEM_PROMPT = """You generate show notes for a podcast episode from its transcript.

Produce a single Markdown document with these sections, in order:

## Summary
2-3 sentences describing what the episode is about.

## Topics
Bulleted list of the main topics in the order they were discussed. Prefix each with the timestamp where the topic begins (use the timestamps embedded in the transcript).

## Mentioned
Group items by kind, only including sections that have entries:
- **People** — anyone named
- **Books / Articles** — titles referenced
- **Projects / Companies / Products** — anything mentioned by name
- **URLs** — any URLs spoken aloud or strongly implied

## Quotable Moments
1-3 short, interesting quotes with timestamps. Skip this section if nothing stands out.

Rules:
- Use HH:MM:SS timestamps when the episode is over an hour long, MM:SS otherwise.
- Be concise. Show notes should be skimmable.
- Do not fabricate. Only include items actually present in the transcript.
- If the transcript is ambiguous about a name or title, prefer omitting it over guessing.
"""


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


def generate_notes(transcript: str, claude_model: str) -> str:
    from anthropic import Anthropic

    client = Anthropic()
    message = client.messages.create(
        model=claude_model,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SHOWNOTES_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
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
    parser.add_argument("audio", type=Path, help="Path to audio file (mp3, wav, m4a, flac, ...)")
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
        default="claude-sonnet-4-6",
        help="Anthropic model id used to generate show notes (default: claude-sonnet-4-6).",
    )
    parser.add_argument(
        "--keep-transcript",
        action="store_true",
        help="Also write the timestamped transcript to <stem>.transcript.txt.",
    )
    parser.add_argument(
        "--transcript-only",
        action="store_true",
        help="Stop after transcribing; do not call Claude.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    sys.exit(_run(argv))


def _run(argv: list[str] | None) -> int:
    args = parse_args(argv)

    if not args.audio.exists():
        print(f"error: audio file not found: {args.audio}", file=sys.stderr)
        return 1

    if not args.transcript_only and not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.audio.stem
    whisper_model = args.whisper_model or default_whisper_model()

    print(f"Transcribing {args.audio} with {whisper_model}...", file=sys.stderr)
    segments = transcribe(args.audio, whisper_model)
    transcript = render_transcript(segments)

    if args.keep_transcript or args.transcript_only:
        transcript_path = args.output_dir / f"{stem}.transcript.txt"
        transcript_path.write_text(transcript)
        print(f"Wrote transcript: {transcript_path}", file=sys.stderr)

    if args.transcript_only:
        return 0

    print(f"Generating show notes with {args.claude_model}...", file=sys.stderr)
    notes = generate_notes(transcript, args.claude_model)

    notes_path = args.output_dir / f"{stem}.shownotes.md"
    notes_path.write_text(notes)
    print(f"Wrote show notes: {notes_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    main()
