import re
import logging
import json
from pathlib import Path
from threading import Event

from crewai import Agent, Crew, LLM, Process, Task

from models import AlignedLine
from pipeline_utils import PipelineCancelledError, call_with_retry, extract_scene_number

logger = logging.getLogger(__name__)

class TweaksPipeline:
    """Tweaks"""

    def __init__(
        self,
        output_dir: str | Path,
        scenes_info: dict = dict(),
        cancel_event: Event | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.cancel_event = cancel_event
        self.scenes_info = scenes_info

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
                        f"\t{al.stem_file_path.replace("outputs_tmp", "outputs")}\t{al.reference_image_path}"
                        f"\t{al.direction_sound}\t{al.direction_lighting}"
                        f"\t{al.direction_drone}\t{al.direction_catapult}"
                        f"\t{al.direction_pause}\t{json.dumps(info["options"])}\n"
                    )
                else:
                    f.write(
                        f"{al.speaker}\t{al.line}\t{al.line_en}\t{al.start_time:.3f}"
                        f"\t{al.stem_file_path.replace("outputs_tmp", "outputs")}\t{al.reference_image_path}"
                        f"\t{al.direction_sound}\t{al.direction_lighting}"
                        f"\t{al.direction_drone}\t{al.direction_catapult}"
                        f"\t{al.direction_pause}\n"
                    )
            return path

    # ------------------------------------------------------------------ #
    #  Run
    # ------------------------------------------------------------------ #
    def run(self, aligned_tsv_paths: list[Path]) -> list[Path]:
        """Tweaks"""
        result_paths: list[Path] = []

        for tsv_path in aligned_tsv_paths:
            if self.cancel_event and self.cancel_event.is_set():
                raise PipelineCancelledError("Cancelled during tweaks")
            scene_num = extract_scene_number(tsv_path)
            lines = self.read_aligned_tsv(tsv_path)
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

    tweaks = TweaksPipeline(
        output_dir=args.dir,
        scenes_info=scenes_info
    )
    result = tweaks.run(aligned_tsvs)
    print(f"\n完了: {len(result)} ファイル")
