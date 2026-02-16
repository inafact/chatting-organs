from pathlib import Path
import wave
from threading import Event

from elevenlabs import ElevenLabs
from elevenlabs.core.api_error import ApiError as ElevenLabsApiError

from models import AlignedLine, DialogueLine
from tts import TTSPipeline
from retry_utils import PipelineCancelledError, call_with_retry

class AlignmentPipeline:
    """WAV + TSV → ElevenLabs Forced Alignment → タイムスタンプ付き TSV

    ElevenLabs の Forced Alignment はダイアライゼーション(話者ラベル)非対応
    のため、セリフ本文のみを連結してアライメントし、文字オフセットで
    各行の開始時刻を逆引きする。
    """

    def __init__(
        self,
        output_dir: str | Path,
        api_key: str | None = None,
        main_locale: str = "ja",
        cancel_event: Event | None = None,
    ):
        self.client = ElevenLabs(api_key=api_key)  # ELEVENLABS_API_KEY env fallback
        self.output_dir = Path(output_dir)
        self.main_locale = main_locale
        self.cancel_event = cancel_event

    # ------------------------------------------------------------------ #
    #  Core: 1シーン分のアライメント
    # ------------------------------------------------------------------ #
    def align_scene(
        self,
        lines: list[DialogueLine],
        wav_path: Path,
    ) -> list[AlignedLine]:
        # セリフ本文だけを改行で連結（話者ラベルは入れない）
        parts = [dl.line for dl in lines] if self.main_locale == "ja" else [dl.line_en for dl in lines]
        transcript = "\n".join(parts)

        # 各行の先頭文字が transcript 内の何文字目かを記録
        offsets: list[int] = []
        pos = 0
        for part in parts:
            offsets.append(pos)
            pos += len(part) + 1  # +1 = "\n"

        # ElevenLabs Forced Alignment
        def _do_alignment():
            with open(wav_path, "rb") as f:
                return self.client.forced_alignment.create(
                    file=f,
                    text=transcript,
                )

        result = call_with_retry(
            _do_alignment,
            max_retries=3,
            base_delay=3.0,
            retryable_exceptions=(ElevenLabsApiError, ConnectionError, TimeoutError),
            cancel_event=self.cancel_event,
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
                    line_en=dl.line_en,
                    start_time=round(start, 3),
                    stem_file_path=""
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
                f.write(
                  f"{al.speaker}\t{al.line}\t{al.line_en}\t{al.start_time:.3f}\t{al.stem_file_path}\n"
                )
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
            if self.cancel_event and self.cancel_event.is_set():
                raise PipelineCancelledError("Cancelled during alignment")

            wav_path = wav_by_stem.get(tsv_path.stem)
            if wav_path is None:
                print(f"  スキップ: {tsv_path.name} に対応する WAV なし")
                continue

            print(f"\n  アライメント: {tsv_path.name} + {wav_path.name}")
            lines = TTSPipeline.read_tsv(tsv_path)
            aligned = self.align_scene(lines, wav_path)

            # split each dialogue turn
            swav_path: str = str(wav_path)

            with wave.open(swav_path, "rb") as wf:
              elapsed: float = 0
              ioffset: float = 0
              sr: int = wf.getframerate()

              for i, al in enumerate(aligned):
                frame_start = min(int(sr * elapsed), wf.getnframes())
                wf.setpos(frame_start)
                if i == 0:
                  ioffset = al.start_time
                else:
                  st_f = al.start_time - ioffset
                  diff_t = st_f - elapsed
                  numframes = int(sr * diff_t)
                  data_pcm = bytearray()
                  data_pcm.extend(wf.readframes(numframes))
                  stem_file_path = Path(swav_path.replace(".wav", f"_{frame_start}.wav"))
                  TTSPipeline._save_wav(bytes(data_pcm), stem_file_path)
                  aligned[i - 1].stem_file_path = str(stem_file_path.absolute())
                  elapsed = elapsed + diff_t

              # one more
              frame_start = min(int(sr * elapsed), wf.getnframes())
              wf.setpos(frame_start)
              numframes = wf.getnframes() - frame_start
              data_pcm = bytearray()
              data_pcm.extend(wf.readframes(numframes))
              stem_file_path = Path(swav_path.replace(".wav", f"_{frame_start}.wav"))
              TTSPipeline._save_wav(bytes(data_pcm), stem_file_path)
              aligned[-1].stem_file_path = str(stem_file_path.absolute())

            # all_aligned.extend(aligned)
            out = self._write_aligned_tsv(
              aligned, tsv_path.stem + "_aligned.tsv"
            )
            result_paths.append(out)

            print(f"    -> {out}  ({len(aligned)} 行)")

        # 全シーン統合
        # if len(result_paths) > 1:
        #     combined = self._write_aligned_tsv(all_aligned, "all_scenes_aligned.tsv")
        #     print(f"\n  統合アライメント TSV: {combined}")

        return result_paths


if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    import tomllib
    load_dotenv()

    parser = argparse.ArgumentParser(description="Forced Alignment (ElevenLabs)")
    parser.add_argument("dir", type=Path, help="scene_*.tsv と scene_*.wav を含むディレクトリ")
    args = parser.parse_args()

    tsv_files = sorted(args.dir.glob("scene_*.tsv"))
    wav_files = sorted(args.dir.glob("scene_*.wav"))

    with open("./app_config.toml", "rb") as f:
      data = tomllib.load(f)
      if "main_locale" in data:
        print("loading [main_locale]..")
        main_locale = data["main_locale"]
      print("loaded from app_config.yml..")
      print(main_locale)

    aligner = AlignmentPipeline(
      output_dir=args.dir,
      main_locale=args.main_locale
    )
    result = aligner.run(tsv_files, wav_files)

    print(f"\n完了: {len(result)} ファイル")
