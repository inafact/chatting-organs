"""generate_schedule.py — スケジュール付きバッチ生成

Usage:
    uv run python generate_schedule.py [--weekday|--weekend]
                                       [--output PATH]
                                       [--ja-config PATH] [--en-config PATH]
                                       [--max-retries N] [--no-validate]
"""
import argparse
import json
import os
import threading
import tomllib
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from alignment import AlignmentPipeline
from direction import DirectionPipeline
from image_search import ImageSearchPipeline
from dialogue import DialoguePipeline
from pipeline_utils import PipelineCancelledError
from tts import TTSPipeline
from tweaks import TweaksPipeline
from validation import Validator

# ---------------------------------------------------------------------------
# Schedule constants
# ---------------------------------------------------------------------------
ALL_HOURS = [11, 12, 13, 14, 15, 16, 17, 18]
WEEKDAY_SKIP = {11, 12}
MINUTE = 25  # every hour at :25


def _locale_for_hour(hour: int) -> str:
    return "ja" if hour % 2 == 1 else "en"


def build_slots(is_weekday: bool) -> list[tuple[str, str]]:
    """Return list of (time_str, locale) pairs for the day."""
    slots = []
    for h in ALL_HOURS:
        if is_weekday and h in WEEKDAY_SKIP:
            continue
        slots.append((f"{h:02d}:{MINUTE:02d}", _locale_for_hour(h)))
    return slots


def build_schedule(
    slots: list[tuple[str, str]],
    ja_outputs: list[str],
    en_outputs: list[str],
) -> dict[str, str]:
    schedule: dict[str, str] = {}
    ja_idx = 0
    en_idx = 0
    for time_str, locale in slots:
        if locale == "ja":
            schedule[time_str] = ja_outputs[ja_idx % len(ja_outputs)]
            ja_idx += 1
        else:
            schedule[time_str] = en_outputs[en_idx % len(en_outputs)]
            en_idx += 1
    return schedule


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------
def _load_config(config_path: str) -> dict:
    defaults = {
        "main_locale": "ja",
        "render_scenes": {},
        "directors_notes": [],
        "image_search": {
            "enabled": False,
            "images_dir": "images",
            "model_name": "ViT-B-32",
            "similarity_threshold": 0.245,
            "search_src": "line_en",
        },
        "direction": {
            "enabled": False,
            "prompt_path": "direction_prompt_example.txt",
        },
    }
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    for key in ("main_locale", "render_scenes", "directors_notes"):
        if key in data:
            defaults[key] = data[key]
    if "image_search" in data:
        defaults["image_search"].update(data["image_search"])
    if "direction" in data:
        defaults["direction"].update(data["direction"])
    return defaults


def _print_issues(issues: list) -> None:
    for issue in issues:
        loc = f"シーン{issue.scene}" + (f" 行{issue.line}" if issue.line else "")
        print(f"  [{'ERROR' if issue.is_error else 'WARN'}] [{issue.check}] {loc}: {issue.message}")


def run_pipeline_once(config_path: str, max_retries: int = 2, validate: bool = True) -> str:
    """パイプラインを実行し、各ステージ直後にバリデーションとリトライを行う。

    リトライ戦略:
      - line_count エラー (dialogue 直後): セリフ生成からフル再実行
      - audio_duration エラー (alignment 直後): WAV+aligned TSV を破棄して TTS からやり直し
      - direction_tags エラー (tweaks 直後): direction + tweaks のみ再実行
    """
    load_dotenv()
    cfg = _load_config(config_path)

    main_locale: str = cfg["main_locale"]
    render_scenes: dict = cfg["render_scenes"]
    directors_notes: list = cfg["directors_notes"]
    image_search_config: dict = cfg["image_search"]
    direction_config: dict = cfg["direction"]
    direction_enabled = direction_config.get("enabled", False)

    cancel_event = threading.Event()

    # ── 1. Dialogue generation + line_count validation ────────────────────
    pipeline = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"\n[Validation] line_count エラー → セリフ再生成 ({attempt}/{max_retries})")

        pipeline = DialoguePipeline(
            prompt_path="prompt_example.txt",
            model=os.getenv("GEMINI_LLM_MODEL", "gpt-4o"),
            temperature=float(os.getenv("TEMPERATURE", "0.8")),
            main_locale=main_locale,
            render_scenes=render_scenes,
            cancel_event=cancel_event,
        )
        results = pipeline.run()
        total = sum(r.char_count for r in results)
        print(f"\nセリフ生成完了: 全 {len(results)} シーン / 合計 {total} 字")

        if not validate:
            break

        issues = Validator(pipeline.output_dir, main_locale).check_line_counts()
        if not any(i.is_error for i in issues):
            break
        _print_issues(issues)
        if attempt == max_retries:
            print("[Validation] line_count: 最大リトライ回数に達した。続行")

    # ── 2. TTS + Alignment + audio_duration validation ────────────────────
    aligned_tsvs: list[Path] = []
    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"\n[Validation] audio_duration エラー → TTS+Alignment 再実行 ({attempt}/{max_retries})")
            for f in pipeline.output_dir.glob("*.wav"):
                f.unlink()
            for f in pipeline.output_dir.glob("*_aligned.tsv"):
                f.unlink()

        tts = TTSPipeline(
            output_dir=pipeline.output_dir,
            voices={"<ドローン>": "Vindemiatrix", "<カタパルト>": "Zubenelgenubi"},
            model=os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-tts"),
            chunk_max_bytes=int(os.getenv("GEMINI_TTS_MAX_CHUNK_BYTES", 5000)),
            director_prompt=directors_notes,
            main_locale=main_locale,
            cancel_event=cancel_event,
        )
        tsv_files = sorted(pipeline.output_dir.glob("scene_*.tsv"))
        wav_files = tts.run(tsv_files)
        print(f"\n音声生成完了: {len(wav_files)} ファイル")

        aligner = AlignmentPipeline(
            output_dir=pipeline.output_dir,
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            main_locale=main_locale,
            cancel_event=cancel_event,
        )
        tsv_files = sorted(pipeline.output_dir.glob("scene_*.tsv"))
        wav_files = sorted(pipeline.output_dir.glob("scene_*.wav"))
        aligned_tsvs = aligner.run(tsv_files, wav_files)
        print(f"\nアライメント完了: {len(aligned_tsvs)} ファイル")

        if not validate:
            break

        issues = Validator(pipeline.output_dir, main_locale).check_audio_durations()
        if not any(i.is_error for i in issues):
            break
        _print_issues(issues)
        if attempt == max_retries:
            print("[Validation] audio_duration: 最大リトライ回数に達した。続行")

    # ── 3. Image search (optional) ────────────────────────────────────────
    if image_search_config.get("enabled", False):
        image_search = ImageSearchPipeline(
            output_dir=pipeline.output_dir,
            images_dir=image_search_config.get("images_dir", "images"),
            model_name=str(image_search_config.get("model_name", "ViT-B-32")),
            similarity_threshold=float(image_search_config.get("similarity_threshold", 0.245)),
            search_src=str(image_search_config.get("search_src", "line_en")),
            scenes_info=render_scenes,
            cancel_event=cancel_event,
        )
        aligned_tsvs = image_search.run(aligned_tsvs)
        print(f"\n画像検索完了: {len(aligned_tsvs)} ファイル")

    # ── 4. Direction (optional) ───────────────────────────────────────────
    if direction_enabled:
        direction_pipeline = DirectionPipeline(
            output_dir=pipeline.output_dir,
            prompt_path=str(direction_config.get("prompt_path", "direction_prompt_example.txt")),
            model=os.getenv("GEMINI_LLM_MODEL", "gpt-4o"),
            scenes_info=render_scenes,
            cancel_event=cancel_event,
        )
        aligned_tsvs = direction_pipeline.run(aligned_tsvs)
        print(f"\n演出指示生成完了: {len(aligned_tsvs)} ファイル")

    # ── 5. Tweaks + rename outputs_tmp → outputs ──────────────────────────
    tweaks_pipeline = TweaksPipeline(
        output_dir=pipeline.output_dir,
        scenes_info=render_scenes,
        cancel_event=cancel_event,
    )
    tweaks_pipeline.run(aligned_tsvs)

    prod_dir_str = str(pipeline.output_dir).replace("_tmp", "")
    prod_dir: Path = pipeline.output_dir.replace(prod_dir_str)
    print(f"[PIPELINE FINISHED] → {prod_dir}")

    # ── 6. Direction tags validation + direction-only retry ───────────────
    if validate and direction_enabled:
        for attempt in range(max_retries + 1):
            issues = Validator(prod_dir, main_locale).check_direction_tags()
            if not any(i.is_error for i in issues):
                break
            _print_issues(issues)
            if attempt < max_retries:
                print(f"\n[Validation] direction_tags エラー → direction 再実行 ({attempt + 1}/{max_retries})")
                _run_direction_tweaks(prod_dir, cfg)
            else:
                print("[Validation] direction_tags: 最大リトライ回数に達した。続行")

    return prod_dir.resolve().as_posix()


# ---------------------------------------------------------------------------
# direction + tweaks のみ再実行 (prod_dir 上で)
# ---------------------------------------------------------------------------
def _run_direction_tweaks(prod_dir: Path, cfg: dict) -> None:
    """outputs/ ディレクトリで direction + tweaks のみ再実行する。"""
    render_scenes = cfg["render_scenes"]
    direction_config = cfg["direction"]
    cancel_event = threading.Event()

    aligned_tsvs = sorted(prod_dir.glob("scene_*_aligned.tsv"))

    direction_pipeline = DirectionPipeline(
        output_dir=prod_dir,
        prompt_path=str(direction_config.get("prompt_path", "direction_prompt_example.txt")),
        model=os.getenv("GEMINI_LLM_MODEL", "gpt-4o"),
        scenes_info=render_scenes,
        cancel_event=cancel_event,
    )
    aligned_tsvs = direction_pipeline.run(aligned_tsvs)

    tweaks_pipeline = TweaksPipeline(
        output_dir=prod_dir,
        scenes_info=render_scenes,
        cancel_event=cancel_event,
    )
    tweaks_pipeline.run(aligned_tsvs)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="スケジュール付きバッチ生成")
    day_group = parser.add_mutually_exclusive_group()
    day_group.add_argument("--weekday", action="store_true",
                           help="平日スケジュール (11・12時スキップ、ja×3+en×3=計6回)")
    day_group.add_argument("--weekend", action="store_true",
                           help="休日スケジュール (全8枠、ja×4+en×4=計8回)")
    parser.add_argument("--output", default="schedule.json", metavar="PATH",
                        help="出力JSONパス (default: schedule.json)")
    parser.add_argument("--ja-config", default="app_config.toml", metavar="PATH",
                        help="日本語用設定ファイル (default: app_config.toml)")
    parser.add_argument("--en-config", default="app_config_en.toml", metavar="PATH",
                        help="英語用設定ファイル (default: app_config_en.toml)")
    parser.add_argument("--max-retries", type=int, default=5, metavar="N",
                        help="バリデーション失敗時のフル再実行上限 (default: 5)")
    parser.add_argument("--no-validate", action="store_true",
                        help="バリデーションをスキップする")
    args = parser.parse_args()

    # Determine weekday/weekend
    if args.weekday:
        is_weekday = True
    elif args.weekend:
        is_weekday = False
    else:
        is_weekday = date.today().weekday() < 5  # Mon–Fri = 0–4

    day_type = "平日" if is_weekday else "休日"
    slots = build_slots(is_weekday)

    # 必要な生成回数をスロット数から自動算出 (毎時異なるデータを使用するため)
    ja_count = sum(1 for _, loc in slots if loc == "ja")
    en_count = sum(1 for _, loc in slots if loc == "en")

    print(f"スケジュール: {day_type} / {len(slots)} 枠")
    print(f"生成回数: ja×{ja_count} + en×{en_count} = 計{ja_count + en_count}回")
    if not args.no_validate:
        print(f"バリデーション: 有効 (最大リトライ {args.max_retries} 回)")

    # Run ja pipelines
    ja_outputs: list[str] = []
    for i in range(ja_count):
        print(f"\n[JA {i + 1}/{ja_count}] 開始")
        path = run_pipeline_once(
            args.ja_config,
            max_retries=args.max_retries,
            validate=not args.no_validate,
        )
        ja_outputs.append(path)
        print(f"[JA {i + 1}/{ja_count}] 完了 → {path}")

    # Run en pipelines
    en_outputs: list[str] = []
    for i in range(en_count):
        print(f"\n[EN {i + 1}/{en_count}] 開始")
        path = run_pipeline_once(
            args.en_config,
            max_retries=args.max_retries,
            validate=not args.no_validate,
        )
        en_outputs.append(path)
        print(f"[EN {i + 1}/{en_count}] 完了 → {path}")

    # Build and write schedule
    schedule = build_schedule(slots, ja_outputs, en_outputs)
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)

    print(f"\nスケジュール生成完了: {output_path}")
    for time_str, path in schedule.items():
        print(f"  {time_str} → {path}")


if __name__ == "__main__":
    main()
