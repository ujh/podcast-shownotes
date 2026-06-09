# podcast-shownotes

Generate podcast show notes from a local audio file. Transcribes locally with
Whisper, then asks Claude to produce a Markdown summary, topic list, mentioned
people / books / projects / URLs, and quotable moments.

No audio is sent to a third party — only the resulting transcript is sent to
the Claude API to write the notes.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for dependency management
- [ffmpeg](https://ffmpeg.org/) on `PATH` (Whisper uses it to decode audio)
- An Anthropic API key (`ANTHROPIC_API_KEY`)

On Apple Silicon, transcription uses [`mlx-whisper`](https://github.com/ml-explore/mlx-examples/tree/main/whisper)
for Metal GPU acceleration. On other platforms it falls back to
[`faster-whisper`](https://github.com/SYSTRAN/faster-whisper).

## Install

```bash
git clone https://github.com/ujh/podcast-shownotes.git
cd podcast-shownotes
uv sync
```

## Use

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run shownotes path/to/episode.mp3
```

This writes `episode.shownotes.md` to the current directory.

### Useful flags

| Flag | Default | Notes |
|------|---------|-------|
| `-o`, `--output-dir DIR` | `.` | Where to write outputs. |
| `--whisper-model NAME` | `mlx-community/whisper-large-v3-turbo` on Apple Silicon, `large-v3-turbo` elsewhere | Pick a smaller model (e.g. `mlx-community/whisper-base`) for faster but lower-quality transcripts. |
| `--claude-model ID` | `claude-sonnet-4-6` | Any Anthropic model id. |
| `--keep-transcript` | off | Also write the timestamped transcript. |
| `--transcript-only` | off | Stop after transcribing; do not call Claude. |

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
2. **Summarize.** The transcript is sent to Claude with a system prompt
   describing the show-notes format. The system prompt is marked for prompt
   caching so repeated runs against the same model are cheaper.
3. **Write.** The model's reply is written verbatim as Markdown.

## Cost

Transcription is free (local). The Claude call uses roughly one input token
per word of transcript plus a few hundred output tokens. A 60-minute episode
is on the order of 10–15k input tokens; pricing depends on the model you pick.

## License

MIT
