# podcast-shownotes

Generate show notes for the [Expanding Beyond](https://expandingbeyond.it/)
podcast from a local audio file. Transcribes the episode locally with Whisper,
then asks Claude (Opus by default) to write Markdown notes in the show's house
style: a handful of title suggestions, a short conversational summary, a flat
list of mentioned items with links, and a few quotable moments. References
the model can't pin down are surfaced inline as "Needs review" annotations so
a human reviewer can resolve them in one place instead of re-listening.

The prompt is tuned to Expanding Beyond's tone, host names (Monica and Urban),
and existing feed format. If you fork this for a different podcast, edit
`SHOWNOTES_SYSTEM_PROMPT` in `src/podcast_shownotes/__init__.py`.

No audio is sent to a third party — only the resulting transcript is sent to
the Claude API to write the notes.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for dependency management
- [ffmpeg](https://ffmpeg.org/) on `PATH` (Whisper uses it to decode audio)
- The [`claude`](https://docs.claude.com/en/docs/claude-code) CLI, signed in
  to a Claude subscription **or** an `ANTHROPIC_API_KEY`

On Apple Silicon, transcription uses [`mlx-whisper`](https://github.com/ml-explore/mlx-examples/tree/main/whisper)
for Metal GPU acceleration. On other platforms it falls back to
[`faster-whisper`](https://github.com/SYSTRAN/faster-whisper).

## Install

```bash
git clone https://github.com/ujh/podcast-shownotes.git
cd podcast-shownotes
uv sync
```

## Authenticate

You can use either a Claude subscription (recommended for personal use, no
per-token billing) or a direct API key.

### Option 1 — Claude subscription (OAuth token, default)

```bash
uv run shownotes --login
```

This runs `claude setup-token`, walks you through the browser flow, then
caches the resulting OAuth token at
`~/.config/podcast-shownotes/oauth-token` (mode `600`).

Subsequent runs reuse the cached token. To rotate, delete the file or rerun
`--login`.

### Option 2 — API key

Export `ANTHROPIC_API_KEY` in your shell. The script prefers it over the
cached OAuth token when both are present.

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
```

## Use

```bash
uv run shownotes path/to/episode.mp3
```

This writes `episode.shownotes.md` to the current directory.

### Useful flags

| Flag | Default | Notes |
|------|---------|-------|
| `-o`, `--output-dir DIR` | `.` | Where to write outputs. |
| `--whisper-model NAME` | `mlx-community/whisper-large-v3-turbo` on Apple Silicon, `large-v3-turbo` elsewhere | Pick a smaller model (e.g. `mlx-community/whisper-base`) for faster but lower-quality transcripts. |
| `--claude-model ID` | `claude-opus-4-7` | Any Anthropic model id. |
| `--transcript-only` | off | Stop after transcribing; do not call Claude. |
| `--force-transcribe` | off | Re-run Whisper even if a cached transcript exists. |
| `--login` | off | Re-run `claude setup-token` and re-cache the token, then exit. |

### Example

```bash
uv run shownotes "Expanding Beyond EP 63.mp3"
```

Produces:
- `Expanding Beyond EP 63.transcript.txt` — timestamped transcript
- `Expanding Beyond EP 63.shownotes.md` — show notes

The transcript is always written and is reused on subsequent runs for the same
audio file. This makes iterating on the show-notes prompt or swapping the
Claude model cheap — only the summarization step re-runs. Pass
`--force-transcribe` to discard the cached transcript and start over.

## Output format

The generated `*.shownotes.md` follows the Expanding Beyond house style:

- **Title suggestions** — three to five short, conversational episode titles
  in the style of past episodes ("The one where we talk about AI", "Keep
  your database close").
- **Summary** — one to three sentences naming the hosts; light and a bit
  wry, not a corporate abstract.
- **Mentioned** — a flat list of people, projects, tools, books, and URLs,
  Markdown-linked where the URL is canonical or spoken aloud.
- **Quotable moments** — one to four short, timestamped quotes.

When the transcript clearly references something the model cannot
confidently identify or link (an unfamiliar guest, a half-mumbled book
title, a podcast episode named only by topic), the item still appears in
the Mentioned list and is followed by a `> **Needs review:**` blockquote
that summarizes what was said and gives any clues — language, era, who
recommended it, phonetic spellings, likely candidates — so a human reviewer
can resolve it without re-listening.

## How it works

1. **Transcribe.** Whisper runs locally and emits segments with start
   timestamps. Each segment is formatted as `[MM:SS] text` and joined into a
   single transcript string, then written to
   `<output-dir>/<audio-stem>.transcript.txt`. If that file already exists
   it is reused as-is (skip with `--force-transcribe`).
2. **Resolve credentials.** Order: `ANTHROPIC_API_KEY`, then
   `ANTHROPIC_OAUTH_TOKEN`, then the cached file, then bootstrap via
   `claude setup-token`.
3. **Summarize.** The transcript is sent to Claude with the show-notes
   system prompt. When using an OAuth subscription token, the system prompt
   is prefixed with the Claude Code marker the gateway requires, and the
   request includes the `anthropic-beta: oauth-2025-04-20` header. The
   system prompt is marked for prompt caching so repeated runs against the
   same model are cheaper.
4. **Write.** The model's reply is written verbatim as Markdown.

## License

MIT
