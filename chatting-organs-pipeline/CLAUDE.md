# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CrewAI-based pipeline for generating theatrical dialogue scripts and converting them to multi-speaker audio.

1. **Dialogue generation**: Takes `prompt_example.txt` → CrewAI (OpenAI) → TSV (`話者名\tセリフ`)
2. **Audio generation**: Takes TSV → Gemini TTS (multi-speaker) → WAV files

## Tech Stack

- **Python**: 3.13+ (managed via uv)
- **CrewAI** 1.9.3 (`crewai[tools]`) — dialogue generation orchestration
- **OpenAI** (gpt-4o) — LLM for dialogue writing
- **google-genai** — Gemini TTS for multi-speaker audio
- **python-dotenv** — environment variable management

## Commands

```bash
uv run python main.py          # Run full pipeline (dialogue + TTS)
uv add <package>                # Add dependency
source .venv/Scripts/activate   # Git Bash on Windows
```

## Environment Variables

`.env` file (not committed):
```
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...              # for Gemini TTS
OPENAI_MODEL=gpt-4o            # optional
GEMINI_TTS_MODEL=gemini-2.5-flash-tts  # optional
TEMPERATURE=0.8                 # optional
```

## Architecture

```
main.py            Entry point: dialogue generation -> TTS
pipeline.py        DialoguePipeline (CrewAI agents -> TSV)
tts.py             TTSPipeline (TSV -> Gemini multi-speaker TTS -> WAV)
models.py          Pydantic models: DialogueLine, SceneResult
prompt_example.txt Input prompt (read at runtime)
output_<timestamp>/ Generated TSV + WAV files (gitignored)
```

### Full Pipeline Flow

```
prompt_example.txt
       |
  [planner agent]  -- extract scene constraints, pool selections (seed 9993 + mod)
       |
  [writer agent]   -- generate ~8000 chars dialogue per scene
       |
  parse_lines()    -- regex: "ドローン：..." / "カタパルト：..."
       |
  scene_N.tsv      -- speaker<TAB>line
       |
  TTSPipeline      -- chunk by 4KB -> Gemini multi-speaker TTS
       |
  scene_N.wav      -- PCM 24kHz 16bit mono WAV
  all_scenes.wav   -- combined
```

### Key Constraints

- Scenes generated **sequentially** (each depends on prior context)
- Gemini TTS input limit ~4,000 bytes per request → auto-chunked, PCM concatenated
- 2 speakers max in Gemini multi-speaker TTS (matches ドローン + カタパルト)
- Default voices: ドローン=Kore, カタパルト=Puck (configurable in TTSPipeline)
