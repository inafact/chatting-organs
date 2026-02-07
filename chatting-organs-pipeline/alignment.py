from pathlib import Path

from elevenlabs import ElevenLabs

from models import AlignedLine, DialogueLine
from tts import TTSPipeline


class AlignmentPipeline:
    """WAV + TSV → ElevenLabs Forced Alignment → タイムスタンプ付き TSV

    ElevenLabs の Forced Alignment はダイアライゼーション(話者ラベル)非対応
    のため、セリフ本文のみを連結してアライメントし、文字オフセットで
    各行の開始時刻を逆引きする。
    """

    def __init__(
        self,
        output_dir: str | Path,
        api_key: str | None = None
    ):
        self.client = ElevenLabs(api_key=api_key)  # ELEVENLABS_API_KEY env fallback
        self.output_dir = Path(output_dir)

    # ------------------------------------------------------------------ #
    #  Core: 1シーン分のアライメント
    # ------------------------------------------------------------------ #
    def align_scene(
        self,
        lines: list[DialogueLine],
        wav_path: Path,
    ) -> list[AlignedLine]:
        # セリフ本文だけを改行で連結（話者ラベルは入れない）
        parts = [dl.line for dl in lines]
        transcript = "\n".join(parts)

        # 各行の先頭文字が transcript 内の何文字目かを記録
        offsets: list[int] = []
        pos = 0
        for part in parts:
            offsets.append(pos)
            pos += len(part) + 1  # +1 = "\n"

        # ElevenLabs Forced Alignment
        with open(wav_path, "rb") as f:
            result = self.client.forced_alignment.create(
                file=f,
                text=transcript,
            )

        # char_times = result.character_start_times_seconds
        char_times = result.characters

        aligned: list[AlignedLine] = []
        for dl, offset in zip(lines, offsets):
            if offset < len(char_times):
                start = char_times[offset].start
            elif char_times:
                start = char_times[-1].start
            else:
                start = 0.0

            aligned.append(
                AlignedLine(
                    speaker=dl.speaker,
                    line=dl.line,
                    start_time=round(start, 3),
                )
            )

        return aligned

    # ------------------------------------------------------------------ #
    #  TSV 出力
    # ------------------------------------------------------------------ #
    def _write_aligned_tsv(
        self, aligned: list[AlignedLine], filename: str
    ) -> Path:
        path = self.output_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            for al in aligned:
                f.write(f"{al.speaker}\t{al.line}\t{al.start_time:.3f}\n")
        return path

    # ------------------------------------------------------------------ #
    #  Run
    # ------------------------------------------------------------------ #
    def run(self, tsv_paths: list[Path], wav_paths: list[Path]) -> list[Path]:
        """シーン別 TSV + WAV ペアからアライメント付き TSV を生成"""

        # stem でマッチング (scene_1.tsv <-> scene_1.wav)
        wav_by_stem = {p.stem: p for p in wav_paths}

        all_aligned: list[AlignedLine] = []
        result_paths: list[Path] = []

        for tsv_path in tsv_paths:
            wav_path = wav_by_stem.get(tsv_path.stem)
            if wav_path is None:
                print(f"  スキップ: {tsv_path.name} に対応する WAV なし")
                continue

            print(f"\n  アライメント: {tsv_path.name} + {wav_path.name}")
            lines = TTSPipeline.read_tsv(tsv_path)
            aligned = self.align_scene(lines, wav_path)

            out = self._write_aligned_tsv(
                aligned, tsv_path.stem + "_aligned.tsv"
            )
            result_paths.append(out)
            all_aligned.extend(aligned)

            print(f"    -> {out}  ({len(aligned)} 行)")

        # 全シーン統合
        if len(result_paths) > 1:
            combined = self._write_aligned_tsv(all_aligned, "all_scenes_aligned.tsv")
            print(f"\n  統合アライメント TSV: {combined}")

        return result_paths
