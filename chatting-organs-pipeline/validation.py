"""validation.py — 上演データバリデーター

3種のチェックを提供する:
  1. line_count    : scene_N.tsv の line_en 空欄チェック
  2. audio_duration: aligned TSV の split WAV 長さと文字数比チェック
  3. direction_tags: scene_N_direction.csv の無効タグチェック

Usage (standalone):
    uv run python validation.py <output_dir> [--locale ja|en]
"""
import re
import wave
from dataclasses import dataclass, field
from pathlib import Path

from pipeline_utils import extract_scene_number

# direction.py と揃えておく
VALID_TAGS = {
    "sound", "lighting", "drone", "catapult", "pause",
    "/sound", "/lighting", "/drone", "/catapult", "/pause",
}

# 音声長チェックの閾値
DEFAULT_MIN_DURATION_SEC = 0.2   # これより短い = 事実上無音 / 生成ミス
DEFAULT_MAX_DURATION_SEC = 45.0   # これより長い = 1ターンとして不自然 (会話劇の演出上も不適)
DEFAULT_CPS_MAX = 25.0            # 文字数/秒がこれより高い = 音声が短すぎ or 読み飛ばし


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------
@dataclass
class ValidationIssue:
    scene: int
    line: int | None   # 1-indexed。シーン全体の問題は None
    check: str         # "line_count" | "audio_duration" | "direction_tags"
    message: str
    is_error: bool = True  # False = warning (再実行不要だが記録)


@dataclass
class ValidationResult:
    output_dir: Path
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.is_error for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.is_error)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if not i.is_error)

    def error_checks(self) -> set[str]:
        """エラーが発生しているチェック種別を返す"""
        return {i.check for i in self.issues if i.is_error}

    def scenes_with_errors(self, check: str | None = None) -> set[int]:
        return {
            i.scene for i in self.issues
            if i.is_error and (check is None or i.check == check)
        }

    def summary(self) -> str:
        lines = [f"[Validation] {self.output_dir}"]
        lines.append(f"  エラー: {self.error_count}件 / 警告: {self.warning_count}件")
        for issue in self.issues:
            prefix = "  [ERROR]" if issue.is_error else "  [WARN] "
            loc = f"シーン{issue.scene}" + (f" 行{issue.line}" if issue.line else "")
            lines.append(f"{prefix} [{issue.check}] {loc}: {issue.message}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------
class Validator:
    """生成済み output_dir のバリデーション"""

    def __init__(
        self,
        output_dir: Path | str,
        main_locale: str = "ja",
        min_duration_sec: float = DEFAULT_MIN_DURATION_SEC,
        max_duration_sec: float = DEFAULT_MAX_DURATION_SEC,
        cps_max: float = DEFAULT_CPS_MAX,
    ):
        self.output_dir = Path(output_dir)
        self.main_locale = main_locale
        self.min_duration_sec = min_duration_sec
        self.max_duration_sec = max_duration_sec
        self.cps_max = cps_max

    # ------------------------------------------------------------------ #
    # 1. line_count: scene_N.tsv の line_en 空欄チェック
    # ------------------------------------------------------------------ #
    def check_line_counts(self) -> list[ValidationIssue]:
        """scene_N.tsv で line_en (3列目) が空の行を検出する。
        _aligned.tsv は含めない (3列目はそちらでは line_en として正しく埋まる前提)。
        """
        issues: list[ValidationIssue] = []
        tsv_files = sorted(
            p for p in self.output_dir.glob("scene_*.tsv")
            if "_aligned" not in p.name
        )
        for tsv_path in tsv_files:
            scene = extract_scene_number(tsv_path)
            empty_lines: list[int] = []
            with open(tsv_path, "r", encoding="utf-8") as f:
                for line_idx, row in enumerate(f, start=1):
                    row = row.rstrip("\n")
                    if not row:
                        continue
                    cols = row.split("\t")
                    if len(cols) < 3 or cols[2].strip() == "":
                        empty_lines.append(line_idx)
            if empty_lines:
                issues.append(ValidationIssue(
                    scene=scene,
                    line=None,
                    check="line_count",
                    message=(
                        f"line_en が空の行: {empty_lines} (計{len(empty_lines)}行)"
                    ),
                    is_error=True,
                ))
        return issues

    # ------------------------------------------------------------------ #
    # 2. audio_duration: split WAV 長さチェック
    # ------------------------------------------------------------------ #
    def check_audio_durations(self) -> list[ValidationIssue]:
        """scene_N_aligned.tsv の各行について stem_file_path の WAV を開き、
        音声長が [min_duration_sec, max_duration_sec] の範囲内かを確認する。
        加えて、文字数/秒が cps_max を超えていないかも確認する (短すぎ検出)。
        """
        issues: list[ValidationIssue] = []
        aligned_files = sorted(self.output_dir.glob("scene_*_aligned.tsv"))

        for tsv_path in aligned_files:
            scene = extract_scene_number(tsv_path)
            with open(tsv_path, "r", encoding="utf-8") as f:
                rows = [r.rstrip("\n") for r in f if r.strip()]

            for line_idx, row in enumerate(rows, start=1):
                cols = row.split("\t")
                if len(cols) < 5:
                    continue

                line_ja = cols[1]
                line_en = cols[2] if len(cols) > 2 else ""
                stem_path_str = cols[4]

                text = line_ja if self.main_locale == "ja" else line_en
                char_count = len(text)

                if not stem_path_str:
                    issues.append(ValidationIssue(
                        scene=scene, line=line_idx,
                        check="audio_duration",
                        message="stem_file_path が空",
                        is_error=True,
                    ))
                    continue

                stem_path = Path(stem_path_str)
                if not stem_path.exists():
                    issues.append(ValidationIssue(
                        scene=scene, line=line_idx,
                        check="audio_duration",
                        message=f"WAVファイルが見つからない: {stem_path_str}",
                        is_error=True,
                    ))
                    continue

                try:
                    with wave.open(str(stem_path), "rb") as wf:
                        duration_sec = wf.getnframes() / wf.getframerate()
                except Exception as e:
                    issues.append(ValidationIssue(
                        scene=scene, line=line_idx,
                        check="audio_duration",
                        message=f"WAV読み込みエラー: {e}",
                        is_error=True,
                    ))
                    continue

                # 最短チェック
                if duration_sec < self.min_duration_sec:
                    issues.append(ValidationIssue(
                        scene=scene, line=line_idx,
                        check="audio_duration",
                        message=(
                            f"音声が極端に短い: {duration_sec:.3f}秒"
                            f" (テキスト: {repr(text[:40])})"
                        ),
                        is_error=True,
                    ))
                    continue

                # 最長チェック (会話劇として1ターンが長すぎる)
                if duration_sec > self.max_duration_sec:
                    issues.append(ValidationIssue(
                        scene=scene, line=line_idx,
                        check="audio_duration",
                        message=(
                            f"音声が長すぎる: {duration_sec:.1f}秒"
                            f" (上限 {self.max_duration_sec}秒)"
                        ),
                        is_error=True,
                    ))
                    continue

                # 文字数/秒チェック: 短すぎ検出 (短いセリフは比率チェックを緩める)
                if char_count >= 3:
                    cps = char_count / duration_sec
                    if cps > self.cps_max:
                        issues.append(ValidationIssue(
                            scene=scene, line=line_idx,
                            check="audio_duration",
                            message=(
                                f"音声が短すぎる可能性: {cps:.1f}字/秒"
                                f" ({char_count}字 / {duration_sec:.2f}秒)"
                            ),
                            is_error=True,
                        ))

        return issues

    # ------------------------------------------------------------------ #
    # 3. direction_tags: direction CSV の無効タグチェック
    # ------------------------------------------------------------------ #
    def check_direction_tags(self) -> list[ValidationIssue]:
        """scene_N_direction.csv を読み、VALID_TAGS 外のタグが含まれる行を検出する。
        direction が disabled の場合はファイルが存在しないので自動スキップ。
        """
        issues: list[ValidationIssue] = []
        csv_files = sorted(self.output_dir.glob("scene_*_direction.csv"))

        for csv_path in csv_files:
            scene = extract_scene_number(csv_path)
            try:
                text = csv_path.read_text(encoding="utf-8").strip()
            except Exception as e:
                issues.append(ValidationIssue(
                    scene=scene, line=None,
                    check="direction_tags",
                    message=f"CSVファイル読み込みエラー: {e}",
                    is_error=True,
                ))
                continue

            # markdown コードブロック除去 (direction.py の _parse_direction_csv と同様)
            text = re.sub(r"^```(?:csv)?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)

            for row_num, row in enumerate(text.split("\n"), start=1):
                row = row.strip()
                if not row:
                    continue
                parts = row.split(",")
                if len(parts) < 3:
                    issues.append(ValidationIssue(
                        scene=scene, line=row_num,
                        check="direction_tags",
                        message=f"列数不足 (期待:3+, 実際:{len(parts)}): {row!r}",
                        is_error=True,
                    ))
                    continue
                tag = parts[1].strip().lower()
                if tag not in VALID_TAGS:
                    issues.append(ValidationIssue(
                        scene=scene, line=row_num,
                        check="direction_tags",
                        message=f"無効なタグ '{tag}': {row!r}",
                        is_error=True,
                    ))

        return issues

    # ------------------------------------------------------------------ #
    # まとめて実行
    # ------------------------------------------------------------------ #
    def run_all(self) -> ValidationResult:
        result = ValidationResult(output_dir=self.output_dir)
        result.issues.extend(self.check_line_counts())
        result.issues.extend(self.check_audio_durations())
        result.issues.extend(self.check_direction_tags())
        return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="上演データバリデーター")
    parser.add_argument("output_dir", type=Path, help="outputs/<timestamp>_<locale> ディレクトリ")
    parser.add_argument("--locale", default="ja", choices=["ja", "en"],
                        help="main_locale (default: ja)")
    parser.add_argument("--min-duration", type=float, default=DEFAULT_MIN_DURATION_SEC,
                        help=f"ターン最短秒数 (default: {DEFAULT_MIN_DURATION_SEC})")
    parser.add_argument("--max-duration", type=float, default=DEFAULT_MAX_DURATION_SEC,
                        help=f"ターン最長秒数 (default: {DEFAULT_MAX_DURATION_SEC})")
    parser.add_argument("--cps-max", type=float, default=DEFAULT_CPS_MAX,
                        help=f"chars/sec 上限 (default: {DEFAULT_CPS_MAX})")
    parser.add_argument("--no-audio", action="store_true",
                        help="音声長チェックをスキップ")
    parser.add_argument("--no-direction", action="store_true",
                        help="演出タグチェックをスキップ")
    args = parser.parse_args()

    validator = Validator(
        output_dir=args.output_dir,
        main_locale=args.locale,
        min_duration_sec=args.min_duration,
        max_duration_sec=args.max_duration,
        cps_max=args.cps_max,
    )

    result = ValidationResult(output_dir=args.output_dir)
    result.issues.extend(validator.check_line_counts())
    if not args.no_audio:
        result.issues.extend(validator.check_audio_durations())
    if not args.no_direction:
        result.issues.extend(validator.check_direction_tags())

    print(result.summary())
    sys.exit(1 if result.has_errors else 0)
