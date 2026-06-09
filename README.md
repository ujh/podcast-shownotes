# podcast-shownotes

Generate podcast show notes from a local audio file. Transcribes locally with
Whisper, then asks Claude (Opus by default) to produce a Markdown summary,
topic list, mentioned people / books / projects / URLs, and quotable moments.

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
| `--keep-transcript` | off | Also write the timestamped transcript. |
| `--transcript-only` | off | Stop after transcribing; do not call Claude. |
| `--login` | off | Re-run `claude setup-token` and re-cache the token, then exit. |

### Example

```bash
uv run shownotes ~/Downloads/ep-42.mp3 -o ~/Notes --keep-transcript
```

Produces:
- `~/Notes/ep-42.transcript.txt` — timestamped transcript
- `~/Notes/ep-42.shownotes.md` — show notes

## How it works

1. **Transcribe.** Whisper runs locally and emits segments with start
   timestamps. Each segment is formatted as `[MM:SS] text` and joined into a
   single transcript string.
2. **Resolve credentials.** Order: `ANTHROPIC_API_KEY`, then
   `ANTHROPIC_OAUTH_TOKEN`, then the cached file, then bootstrap via
   `claude setup-token`.
3. **Summarize.** The transcript is sent to Claude with a system prompt
   describing the show-notes format. When using an OAuth subscription token,
   the system prompt is prefixed with the Claude Code marker the gateway
   requires, and the request includes the `anthropic-beta: oauth-2025-04-20`
   header. The system prompt is marked for prompt caching so repeated runs
   against the same model are cheaper.
4. **Write.** The model's reply is written verbatim as Markdown.

## License

MIT
