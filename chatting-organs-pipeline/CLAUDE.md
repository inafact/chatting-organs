# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CrewAI-based pipeline for generating theatrical dialogue scripts, converting them to multi-speaker audio, and producing time-aligned transcripts. Controlled via OSC messages.

1. **Dialogue generation**: Takes `prompt_example.txt` → CrewAI (LLM) → TSV (`話者名\tセリフ\tセリフ英訳`)
2. **English translation**: Translator agent produces line-by-line English translations (included in TSV)
3. **Audio generation**: Takes TSV → Gemini TTS (multi-speaker) → WAV files
4. **Forced alignment**: Takes TSV + WAV → ElevenLabs Forced Alignment → タイムスタンプ付き TSV + per-turn WAV splits

## Tech Stack

- **Python**: 3.13+ (managed via uv)
- **CrewAI** 1.9.3 (`crewai[tools]`) — dialogue generation orchestration
- **LLM** (gpt-4o default, configurable) — dialogue writing
- **google-genai** — Gemini TTS for multi-speaker audio
- **elevenlabs** — Forced Alignment API for timing extraction
- **python-osc** — OSC server/client for inter-process communication
- **python-dotenv** — environment variable management

## Commands

```bash
uv run python main.py          # Start OSC server (listens on port 12000)
uv add <package>                # Add dependency
source .venv/Scripts/activate   # Git Bash on Windows
```

### OSC Messages

- `/run_pipeline` — trigger full pipeline (optional args: voice names)
- `/reload_env` — reload `.env` file
- `/reload_configs` — reload `app_config.toml`

## Environment Variables

`.env` file (not committed):
```
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...              # for Gemini TTS
ELEVENLABS_API_KEY=...          # for Forced Alignment
GEMINI_LLM_MODEL=gpt-4o        # optional, LLM model for dialogue generation
GEMINI_TTS_MODEL=gemini-2.5-flash-tts  # optional
TEMPERATURE=0.8                 # optional
OSC_RECV_HOST=0.0.0.0           # optional, OSC server bind address
OSC_RECV_PORT=12000             # optional, OSC server port
PLAYER_OSC_ADDR=127.0.0.1      # optional, player OSC target address
PLAYER_OSC_PORT=10001           # optional, player OSC target port
```

## Architecture

```
main.py            OSC server + PipelineManager (orchestrates all 3 stages)
pipeline.py        DialoguePipeline (CrewAI planner+writer+translator agents -> TSV)
tts.py             TTSPipeline (TSV -> Gemini multi-speaker TTS -> WAV)
alignment.py       AlignmentPipeline (WAV+TSV -> ElevenLabs Forced Alignment -> aligned TSV + split WAVs)
models.py          Pydantic models: DialogueLine(+line_en), AlignedLine(+line_en), SceneResult
app_config.toml    Runtime config: render_scenes (scene definitions) + directors_notes (TTS演出指示)
prompt_example.txt Input prompt (read at runtime)
outputs/<timestamp>/ Generated TSV + WAV files (gitignored)
```

### Full Pipeline Flow

```
prompt_example.txt + app_config.toml
       |
  [planner agent]  -- extract scene constraints, pool selections (random seed + mod)
       |
  [writer agent]   -- generate dialogue per scene (length configurable per scene)
       |
  [translator agent] -- translate each line to English
       |
  parse_lines()    -- regex: "ドローン：..." / "カタパルト：..."
       |
  scene_N.tsv      -- speaker<TAB>line<TAB>line_en
       |
  TTSPipeline      -- chunk by 5KB -> Gemini multi-speaker TTS (with directors_notes)
       |
  scene_N.wav      -- PCM 24kHz 16bit mono WAV
       |
  AlignmentPipeline -- ElevenLabs Forced Alignment
       |
  scene_N_aligned.tsv  -- speaker<TAB>line<TAB>line_en<TAB>start_time<TAB>stem_file_path
  scene_N_<offset>.wav -- per-turn split WAV files
```

### Key Constraints

- Scenes generated **sequentially** (each depends on prior context)
- Scene definitions (label, setting, length) are configurable via `app_config.toml`
- Gemini TTS input limit ~5,000 bytes per request → auto-chunked, PCM concatenated
- Director's notes per scene index passed to Gemini TTS for vocal style control
- 2 speakers max in Gemini multi-speaker TTS (matches ドローン + カタパルト)
- Default voices: ドローン=Kore, カタパルト=Enceladus (overridable via OSC args or constructor)
- ElevenLabs Forced Alignment does not support diarization → character offset mapping used
- Per-turn WAV splitting based on aligned timestamps
- Translator agent produces line-by-line English translations; line count mismatch handled gracefully (defaults to empty string)
- TSV format: dialogue TSV is 3-column (`speaker\tline\tline_en`), aligned TSV is 5-column (`speaker\tline\tline_en\tstart_time\tstem_file_path`)
- TTS/Alignment pipelines read `line_en` from TSV and pass it through; TTS uses only Japanese lines for audio generation
