# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CrewAI-based pipeline for generating theatrical dialogue scripts, converting them to multi-speaker audio, producing time-aligned transcripts, and matching semantic images. Controlled via OSC messages.

1. **Dialogue generation**: Takes `prompt_example.txt` → CrewAI (LLM) → TSV (`話者名\tセリフ\tセリフ英訳`)
2. **English translation**: Translator agent produces line-by-line English translations (included in TSV)
3. **Audio generation**: Takes TSV → Gemini TTS (multi-speaker) → WAV files
4. **Forced alignment**: Takes TSV + WAV → ElevenLabs Forced Alignment → タイムスタンプ付き TSV + per-turn WAV splits
5. **Image search**: Takes aligned TSV + images/ → OpenCLIP semantic matching → 画像パス付き TSV
6. **Direction generation**: Takes aligned TSV + `direction_prompt_example.txt` → CrewAI (演出家agent) → 演出指示付き TSV (音楽・照明・ドローン・カタパルト)

## Tech Stack

- **Python**: 3.13+ (managed via uv)
- **CrewAI** 1.9.3 (`crewai[tools]`) — dialogue generation orchestration
- **LLM** (gpt-4o default, configurable) — dialogue writing
- **google-genai** — Gemini TTS for multi-speaker audio
- **elevenlabs** — Forced Alignment API for timing extraction
- **python-osc** — OSC server/client for inter-process communication
- **python-dotenv** — environment variable management
- **open-clip-torch** — OpenCLIP vision-language model for semantic image search
- **torch** / **torchvision** — PyTorch (OpenCLIP backend)
- **pillow** — image processing
- **transformers** (`[sentencepiece]`) — tokenizer support
- **polars** — data processing

## Commands

```bash
uv run python main.py          # Start OSC server (listens on port 10000)
uv add <package>                # Add dependency
source .venv/Scripts/activate   # Git Bash on Windows
```

### CLI Mode (standalone execution)

Each pipeline stage can be run independently via `__main__`:

```bash
uv run python tts.py <output_dir> [--config X]               # TTS only
uv run python alignment.py <output_dir> [--config X]         # Alignment only
uv run python image_search.py <output_dir>                   # Image search only
uv run python direction.py <output_dir> [--prompt X] [--config X] # Direction only
uv run python tweaks.py <output_dir>                         # Tweaks only (outputs_tmp→outputs path fix + options JSON)
uv run python credit_generator.py <xlsx>                     # Credit HTML generation
uv run python validation.py <output_dir> [--locale ja|en]   # Validate existing output dir
uv run python generate_schedule.py [--weekday|--weekend] [--output PATH] [--ja-config PATH] [--en-config PATH] [--max-retries N] [--no-validate]  # Batch generation with schedule
```

### OSC Messages

- `/run_pipeline` — trigger full pipeline (optional args: voice names); runs in background thread
- `/cancel_pipeline` — safely cancel a running pipeline
- `/reload_env` — reload `.env` file
- `/reload_configs` — reload `app_config.toml` (optional arg: config file path)

### OSC Reply Codes

| Code | Meaning |
|---|---|
| `1` | Pipeline completed successfully |
| `-1` | Pipeline error (retries exhausted) |
| `-2` | Pipeline cancelled |
| `4` | Cancel request acknowledged |
| `3` | Config reload successful |
| `2` | Env reload successful |
| `0` | Nothing to cancel |

## Environment Variables

`.env` file (not committed):
```
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...              # for Gemini TTS
ELEVENLABS_API_KEY=...          # for Forced Alignment
GEMINI_LLM_MODEL=gpt-4o        # optional, LLM model for dialogue generation
GEMINI_TTS_MODEL=gemini-2.5-flash-tts  # optional
GEMINI_TTS_MAX_CHUNK_BYTES=5000 # optional, chunk size for TTS input
TEMPERATURE=0.8                 # optional
OSC_RECV_HOST=0.0.0.0           # optional, OSC server bind address
OSC_RECV_PORT=10000             # optional, OSC server port
PLAYER_OSC_ADDR=127.0.0.1      # optional, player OSC target address
PLAYER_OSC_PORT=10001           # optional, player OSC target port
```

## Architecture

```
main.py            OSC server + PipelineManager (orchestrates all stages, background thread)
dialogue.py        DialoguePipeline (CrewAI planner+writer+translator agents -> TSV)
tts.py             TTSPipeline (TSV -> Gemini multi-speaker TTS -> WAV)
alignment.py       AlignmentPipeline (WAV+TSV -> ElevenLabs Forced Alignment -> aligned TSV + split WAVs)
image_search.py    ImageSearchPipeline (aligned TSV + images/ -> OpenCLIP semantic matching -> image-ref TSV)
direction.py       DirectionPipeline (aligned TSV + direction prompt -> CrewAI director agent -> 演出指示付き TSV)
tweaks.py          TweaksPipeline (final pass: outputs_tmp→outputs path fix + direction_pause col + options JSON)
validation.py      Validator (output_dir -> ValidationResult; checks line_count / audio_duration / direction_tags)
generate_schedule.py  Batch generation with schedule JSON output; inline validation + partial retries
pipeline_utils.py  call_with_retry (exponential backoff) + PipelineCancelledError + extract_scene_number
models.py          Pydantic models: DialogueLine(+line_en), AlignedLine(+line_en, +reference_image_path, +direction_*, +direction_pause), SceneResult
app_config.toml    Runtime config (ja): main_locale + render_scenes + directors_notes + image_search + direction
app_config_en.toml Runtime config (en): same structure, main_locale = "en"
prompt_example.txt Input prompt (read at runtime)
direction_prompt_example.txt Direction prompt (演出指示生成用プロンプト, read at runtime)
images/            Curated image assets for semantic matching (jpg, png, etc.)
credit_generator.py  CreditGenerator (Excel "credit" column -> 2-column HTML tables with auto-cycling JS)
outputs_tmp/<timestamp>_<locale>/ Pipeline working directory (gitignored)
outputs/<timestamp>_<locale>/     Renamed from outputs_tmp at pipeline completion (gitignored)
schedule.json      Generated schedule: {"HH:MM": "outputs/<timestamp>_<locale>", ...}
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
  parse_lines()    -- regex: "<ドローン>：..." / "<カタパルト>：..."
       |
  scene_N.tsv      -- speaker<TAB>line<TAB>line_en
       |
  TTSPipeline      -- chunk by configurable bytes -> Gemini multi-speaker TTS (with directors_notes)
       |
  scene_N.wav      -- PCM 24kHz 16bit mono WAV
       |
  AlignmentPipeline -- ElevenLabs Forced Alignment
       |
  scene_N_aligned.tsv  -- speaker<TAB>line<TAB>line_en<TAB>start_time<TAB>stem_file_path
  scene_N_<offset>.wav -- per-turn split WAV files
       |
  ImageSearchPipeline -- OpenCLIP semantic image matching (search_src vs images/)
       |
  scene_N_aligned.tsv  -- speaker<TAB>line<TAB>line_en<TAB>start_time<TAB>stem_file_path<TAB>reference_image_path
       |
  DirectionPipeline -- CrewAI director agent (direction_prompt_example.txt + dialogue)
       |
  scene_N_direction.csv  -- CrewAI raw output (debug/reference)
  scene_N_aligned.tsv    -- +direction_sound<TAB>direction_lighting<TAB>direction_drone<TAB>direction_catapult<TAB>direction_pause
       |
  TweaksPipeline   -- outputs_tmp→outputs path fix in stem_file_path, options JSON append
       |
  scene_N_aligned.tsv    -- stem_file_path uses outputs/ dir; 12-column when scene has options (+ JSON on first row)
  [dir renamed: outputs_tmp/<ts>/ → outputs/<ts>/]
```

### Key Constraints

- Scenes generated **sequentially** (each depends on prior context)
- Scene definitions (label, setting, length, options) are configurable via `app_config.toml` `[render_scenes]`
  - `options` dict per scene: `tempo`, `camera`, etc. — serialized as JSON in final TSV's 12th column (first row only)
- `main_locale` in `app_config.toml`: controls TTS and alignment language (`"ja"` or `"en"`)
  - `"ja"` (default): TTS uses Japanese lines, alignment uses Japanese text
  - `"en"`: TTS uses `line_en`, alignment uses `line_en`
- Gemini TTS input limit configurable via `GEMINI_TTS_MAX_CHUNK_BYTES` env var (default 5000) → auto-chunked, PCM concatenated
- Director's notes per scene index passed to Gemini TTS for vocal style control (list in `app_config.toml`)
- 2 speakers max in Gemini multi-speaker TTS (matches <ドローン> + <カタパルト>)
- Default voices: <ドローン>=Vindemiatrix, <カタパルト>=Zubenelgenubi (overridable via OSC args or constructor)
- Voice pool defined in `PipelineManager.voices_gemini` dict (30 Gemini prebuilt voices)
- ElevenLabs Forced Alignment does not support diarization → character offset mapping used
- Per-turn WAV splitting based on aligned timestamps
- Translator agent produces line-by-line English translations; line count mismatch handled gracefully (defaults to empty string)
- TSV format progression:
  - Dialogue TSV: 3-column (`speaker\tline\tline_en`)
  - Aligned TSV: 5-column (+ `start_time\tstem_file_path`)
  - Image-ref TSV: 6-column (+ `reference_image_path`)
  - Direction TSV: 11-column (+ `direction_sound\tdirection_lighting\tdirection_drone\tdirection_catapult\tdirection_pause`)
  - Final TSV: 12-column when scene has `options` (+ JSON options on first row only); TweaksPipeline also rewrites `stem_file_path` from `outputs_tmp/` → `outputs/`
- TTS/Alignment pipelines read `line_en` from TSV and pass it through
- Image search is configurable via `app_config.toml` (`[image_search]` section):
  - `enabled`: bool
  - `images_dir`: string (single directory) or dict (per-scene directories, e.g. `{ 1 = "_data/シーン1", 2 = "_data/シーン2" }`)
  - `model_name`: OpenCLIP model (default `ViT-B-32`, also supports `ViT-B-16` etc.)
  - `similarity_threshold`: float (default 0.245)
  - `search_src`: `"line_en"` or `"line"` — which text field to use for cosine similarity
- Image search choice modes: `TOP` (default), `TOP_N`, `RANDOM`, `RANDOM_N`
- Supported image formats: jpg, jpeg, png, gif, bmp, webp, tiff
- When multiple images exceed the similarity threshold, selection depends on choice mode
- Direction generation is configurable via `app_config.toml` (`[direction]` section): `enabled`, `prompt_path` (default `direction_prompt_example.txt`)
- DirectionPipeline uses a single CrewAI "演出家" agent; LLM model shared with DialoguePipeline via `GEMINI_LLM_MODEL` env var
- Direction CSV format: `[scene-line],[tag],[instruction],[param]` — tags are `/sound`, `/lighting`, `/drone`, `/catapult`, `/pause` (slash-prefixed)
- Direction values in TSV: `指示番号:パラメータ` space-separated for multiple entries per line; empty string if no direction
- Malformed CSV rows from LLM are skipped with warnings (graceful degradation)
- `scenes_info` (from `render_scenes`) is passed to ImageSearchPipeline and DirectionPipeline for per-scene configuration
- `credit_generator.py` is a standalone utility: reads `credit` column from Excel → deduplicates, sorts (numbers → A–Z → あいうえお), pairs into 2-column rows → splits into multiple `<table id="table-{n}">` elements (max 25 rows each) → outputs HTML with auto-cycling JS (shows one table at a time, rotates every 3 s); dark background, Google Fonts

### Validation (`validation.py`)

`Validator` performs three checks on a completed `outputs/<timestamp>_<locale>/` directory:

| Check | Timing in generate_schedule.py | Error condition | Retry action |
|---|---|---|---|
| `line_count` | After DialoguePipeline | `line_en` empty in `scene_N.tsv` | セリフ再生成 (全シーン) |
| `audio_duration` | After AlignmentPipeline | duration < 0.2s, duration > 45s, or cps > 25字/秒 | `*.wav` + `*_aligned.tsv` 削除 → TTS から再実行 |
| `direction_tags` | After TweaksPipeline | VALID_TAGS 外のタグ or 列数不足 in `scene_N_direction.csv` | direction + tweaks のみ再実行 |

- `ValidationResult.has_errors` / `error_checks()` / `scenes_with_errors()` でエラー種別を取得可能
- `--no-validate` フラグでバリデーションをスキップ可能

### Schedule Generation (`generate_schedule.py`)

- スロット構成: 11:25〜18:25 毎時25分、奇数時=ja、偶数時=en
  - 平日: 11・12時スキップ → ja×3 + en×3 = 計6回生成
  - 休日: 全8枠 → ja×4 + en×4 = 計8回生成
- 各スロットに異なる出力を割り当て (round-robin なし)
- `--ja-config` / `--en-config` で言語ごとに別の `app_config.toml` を指定可能
- 出力 `schedule.json`: `{"HH:MM": "<絶対パス>", ...}` 形式

### Error Handling & Cancellation

- Pipeline runs in a **background `threading.Thread`** (daemon); OSC server remains responsive during execution
- All cloud API calls are wrapped with `call_with_retry()` (exponential backoff, defined in `pipeline_utils.py`)
  - Gemini TTS (`tts.py`): `max_retries=3`, `base_delay=3.0s`, retries on `ServerError`/`ConnectionError`/`TimeoutError`/`ValueError` (空レスポンス含む)
  - ElevenLabs (`alignment.py`): `max_retries=3`, `base_delay=3.0s`, retries on `ApiError`/`ConnectionError`/`TimeoutError`
  - CrewAI (`dialogue.py`): `max_retries=2`, `base_delay=5.0s`, retries on `Exception` (CrewAI wraps errors variably)
  - CrewAI (`direction.py`): `max_retries=2`, `base_delay=5.0s`, retries on `Exception` (same as dialogue.py)
- Cancellation via `threading.Event` passed to all pipeline constructors as `cancel_event`
  - Checked at: top of each scene/chunk loop, between pipeline stages in `main.py`
  - Retry backoff uses `cancel_event.wait(timeout=delay)` for instant cancellation during waits
  - Raises `PipelineCancelledError` which is caught in `_run_pipeline_thread`
- On error/cancel, `pipeline_running` is always reset in `finally` block — no restart required
- A failed stage **stops** the entire pipeline (stages are sequential dependencies)
