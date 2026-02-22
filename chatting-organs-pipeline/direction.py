import re
import logging
import json
from pathlib import Path
from threading import Event

from crewai import Agent, Crew, LLM, Process, Task

from models import AlignedLine
from pipeline_utils import PipelineCancelledError, call_with_retry, extract_scene_number

logger = logging.getLogger(__name__)

VALID_TAGS = {
    "sound", "lighting", "drone", "catapult", "pause",
    "/sound", "/lighting", "/drone", "/catapult", "/pause",
}


class DirectionPipeline:
    """Aligned TSV + direction prompt → CrewAI (director agent) → 10-column TSV"""

    def __init__(
        self,
        output_dir: str | Path,
        prompt_path: str | Path = "direction_prompt_example.txt",
        model: str = "gpt-4o",
        scenes_info: dict = dict(),
        cancel_event: Event | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.prompt_text = Path(prompt_path).read_text(encoding="utf-8")
        self.cancel_event = cancel_event
        self.scenes_info = scenes_info

        self.llm = LLM(model=model, max_completion_tokens=16000)

        self.director = Agent(
            role="演出家",
            goal="対話劇の台本に基づき、音楽・照明・ドローン・カタパルトの演出指示を作成する",
            backstory=(
                "演劇の演出家。音楽・照明・ドローン・カタパルトの演出を"
                "対話の内容と流れに合わせて適切に配置する専門家。"
                "プロンプトの演出ルールを正確に守り、"
                "CSV形式で演出指示を出力する。"
            ),
            llm=self.llm,
            verbose=False,
        )

    # ------------------------------------------------------------------ #
    #  Task builder
    # ------------------------------------------------------------------ #
    def _build_direction_task(self, scene_num: int, lines: list[AlignedLine]) -> Task:
        dialogue_text = "\n".join(
            f"[{scene_num}-{i+1}] {al.speaker}：{al.line}"
            for i, al in enumerate(lines)
        )

        description = f"""\
以下の演出プロンプトに従い、シーン{scene_num}の演出指示を作成してください。

=== 演出プロンプト ===
{self.prompt_text}
=== 演出プロンプトここまで ===

【シーン{scene_num}の台本】
{dialogue_text}

【出力ルール】
・各行の形式: [セリフID],[演出要素タグ],[演出指示番号],[パラメータ]
・セリフIDは「{scene_num}-行番号」形式（例: {scene_num}-1, {scene_num}-2, ...）
・演出要素タグは /sound, /lighting, /drone, /catapult, /pause のいずれか
・パラメータは音楽切替エフェクト番号やドローン動作秒数など（不要なら空）
・演出不要な行はCSVに含めない
・CSVヘッダー行は不要、データ行のみ出力
"""
        return Task(
            description=description,
            expected_output=(
                f"シーン{scene_num}の演出指示CSV。"
                "各行が [セリフID],[tag],[instruction],[param] 形式。"
            ),
            agent=self.director,
            output_file=str(self.output_dir / f"scene_{scene_num}_direction.csv"),
        )

    # ------------------------------------------------------------------ #
    #  CSV parse & merge
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_direction_csv(csv_text: str, scene_num: int, num_lines: int) -> dict:
        """Parse LLM CSV output into {line_index: {tag: [entries]}} (0-indexed).

        Each CSV row: scene-line,tag,instruction,param
        Returns dict mapping 0-based line index to direction entries.
        """
        # Strip markdown code block if present
        text = csv_text.strip()
        text = re.sub(r"^```(?:csv)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)

        directions: dict[int, dict[str, list[str]]] = {}

        for row in text.strip().split("\n"):
            row = row.strip()
            if not row:
                continue

            parts = row.split(",")
            if len(parts) < 3:
                logger.warning("[Direction] Skipping malformed row: %s", row)
                continue

            line_id = parts[0].strip()
            tag = parts[1].strip().lower()
            instruction = parts[2].strip()
            param = parts[3].strip() if len(parts) > 3 else ""

            # Validate tag
            if tag not in VALID_TAGS:
                logger.warning("[Direction] Unknown tag '%s' in row: %s", tag, row)
                continue

            # Parse line ID: "scene_num-line_num" → 0-based index
            m = re.match(r"(\d+)-(\d+)", line_id)
            if not m:
                logger.warning("[Direction] Invalid line ID '%s' in row: %s", line_id, row)
                continue

            parsed_scene = int(m.group(1))
            line_num = int(m.group(2))

            if parsed_scene != scene_num:
                logger.warning("[Direction] Scene mismatch: expected %d, got %d", scene_num, parsed_scene)
                continue

            idx = line_num - 1  # 0-based
            if idx < 0 or idx >= num_lines:
                logger.warning("[Direction] Line number %d out of range (1-%d)", line_num, num_lines)
                continue

            if idx not in directions:
                directions[idx] = {}
            if tag not in directions[idx]:
                directions[idx][tag] = []

            # -- TODO: mulitple commands at once
            entry = f"{instruction} {param}" if param else instruction
            directions[idx][tag].append(entry)

        return directions

    @staticmethod
    def _merge_directions(lines: list[AlignedLine], directions: dict) -> None:
        """Merge parsed directions into AlignedLine objects in-place."""
        for idx, tag_map in directions.items():
            al = lines[idx]
            if "/sound" in tag_map:
                al.direction_sound = " ".join(tag_map["/sound"])
            if "/lighting" in tag_map:
                al.direction_lighting = " ".join(tag_map["/lighting"])
            if "/drone" in tag_map:
                al.direction_drone = ",".join(tag_map["/drone"])
            if "/catapult" in tag_map:
                al.direction_catapult = " ".join(tag_map["/catapult"])
            if "/pause" in tag_map:
                al.direction_pause = " ".join(tag_map["/pause"])

    # ------------------------------------------------------------------ #
    #  TSV I/O
    # ------------------------------------------------------------------ #
    @staticmethod
    def read_aligned_tsv(tsv_path: Path) -> list[AlignedLine]:
        lines: list[AlignedLine] = []
        with open(tsv_path, "r", encoding="utf-8") as f:
            for row in f:
                row = row.rstrip("\n")
                if not row:
                    continue
                cols = row.split("\t")
                if len(cols) >= 5:
                    lines.append(AlignedLine(
                        speaker=cols[0],
                        line=cols[1],
                        line_en=cols[2],
                        start_time=float(cols[3]),
                        stem_file_path=cols[4],
                        reference_image_path=cols[5] if len(cols) > 5 else "",
                        direction_sound=cols[6] if len(cols) > 6 else "",
                        direction_lighting=cols[7] if len(cols) > 7 else "",
                        direction_drone=cols[8] if len(cols) > 8 else "",
                        direction_catapult=cols[9] if len(cols) > 9 else "",
                    ))
        return lines

    @staticmethod
    def _write_aligned_tsv(aligned: list[AlignedLine], path: Path, info: dict | None = None) -> Path:
        with open(path, "w", encoding="utf-8") as f:
            for i, al in enumerate(aligned):
                if type(info) is dict and "options" in info and i == 0:
                    print("..add extra column for scene config")
                    f.write(
                        f"{al.speaker}\t{al.line}\t{al.line_en}\t{al.start_time:.3f}"
                        f"\t{al.stem_file_path}\t{al.reference_image_path}"
                        f"\t{al.direction_sound}\t{al.direction_lighting}"
                        f"\t{al.direction_drone}\t{al.direction_catapult}"
                        f"\t{al.direction_pause}\t{json.dumps(info["options"])}\n"
                    )
                else:
                    f.write(
                        f"{al.speaker}\t{al.line}\t{al.line_en}\t{al.start_time:.3f}"
                        f"\t{al.stem_file_path}\t{al.reference_image_path}"
                        f"\t{al.direction_sound}\t{al.direction_lighting}"
                        f"\t{al.direction_drone}\t{al.direction_catapult}"
                        f"\t{al.direction_pause}\n"
                    )
            return path

    # ------------------------------------------------------------------ #
    #  Run
    # ------------------------------------------------------------------ #
    def run(self, aligned_tsv_paths: list[Path]) -> list[Path]:
        """Generate direction instructions and merge into aligned TSVs (10 columns)."""
        result_paths: list[Path] = []

        for tsv_path in aligned_tsv_paths:
            if self.cancel_event and self.cancel_event.is_set():
                raise PipelineCancelledError("Cancelled during direction generation")

            scene_num = extract_scene_number(tsv_path)
            lines = self.read_aligned_tsv(tsv_path)
            print(f"\n  [Direction] 処理中: {tsv_path.name} (シーン{scene_num}, {len(lines)}行)")
            direction_task = self._build_direction_task(scene_num, lines)

            crew = Crew(
                agents=[self.director],
                tasks=[direction_task],
                process=Process.sequential,
                tracing=False,
                verbose=False,
            )

            output = call_with_retry(
                crew.kickoff,
                max_retries=2,
                base_delay=5.0,
                retryable_exceptions=(Exception,),
                cancel_event=self.cancel_event,
            )

            csv_text = output.raw
            directions = self._parse_direction_csv(csv_text, scene_num, len(lines))
            self._merge_directions(lines, directions)
            if len(self.scenes_info) > 0 and str(scene_num) in self.scenes_info:
              self._write_aligned_tsv(lines, tsv_path, self.scenes_info[str(scene_num)])
            else:
              self._write_aligned_tsv(lines, tsv_path)
            result_paths.append(tsv_path)
            print(f"    -> {tsv_path}  ({len(lines)} 行, 10列)")

        return result_paths


if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    import os
    import tomllib
    load_dotenv()

    parser = argparse.ArgumentParser(description="Direction Pipeline (CrewAI)")
    parser.add_argument("dir", type=Path, help="*_aligned.tsv を含むディレクトリ")
    parser.add_argument("--prompt", type=str, default="direction_prompt_example.txt")
    args = parser.parse_args()

    scenes_info = dict()

    with open("./app_config.toml", "rb") as f:
        data = tomllib.load(f)
        if "render_scenes" in data:
            print("loading [render_scenes]..")
            scenes_info.update(data["render_scenes"])
        print("loaded from app_config.yml..")
        print(scenes_info)

    aligned_tsvs = sorted(args.dir.glob("*_aligned.tsv"))

    direction = DirectionPipeline(
        output_dir=args.dir,
        prompt_path=args.prompt,
        model=os.getenv("GEMINI_LLM_MODEL", "gpt-4o"),
        scenes_info=scenes_info
    )
    result = direction.run(aligned_tsvs)
    print(f"\n完了: {len(result)} ファイル")
