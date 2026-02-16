import base64
import wave
from pathlib import Path
from threading import Event

from google import genai
from google.genai import types
from google.genai.errors import ServerError as GeminiServerError

from models import DialogueLine
from retry_utils import PipelineCancelledError, call_with_retry

# 話者 → Gemini prebuilt voice のデフォルトマッピング
DEFAULT_VOICES: dict[str, str] = {
    "<ドローン>": "Vindemiatrix",
    # "<ドローン>": "Kore",
    "<カタパルト>": "Zubenelgenubi",
    # "<カタパルト>": "Puck",
}

# Gemini TTS 入力テキストのバイト上限（余裕を持たせた値）
_CHUNK_MAX_BYTES = 4000


class TTSPipeline:
    """TSV (DialogueLine list) → Gemini multi-speaker TTS → WAV"""

    def __init__(
        self,
        output_dir: str | Path,
        voices: dict[str, str] | None = None,
        model: str = "gemini-2.5-flash-tts",
        chunk_max_bytes: int = _CHUNK_MAX_BYTES,
        director_prompt: str | list[str] = "",
        main_locale: str = "ja",
        cancel_event: Event | None = None,
    ):
        self.client = genai.Client()  # GOOGLE_API_KEY or GEMINI_API_KEY env var
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.voices = voices or DEFAULT_VOICES.copy()
        # self.voices_marker = "_".join(self.voices.values()).lower()
        self.model = model
        self.chunk_max_bytes = chunk_max_bytes
        self.director_prompt = director_prompt
        self.current_scene_index = 0
        self.main_locale = main_locale
        self.cancel_event = cancel_event

    # ------------------------------------------------------------------ #
    #  TSV I/O
    # ------------------------------------------------------------------ #
    @staticmethod
    def read_tsv(tsv_path: str | Path) -> list[DialogueLine]:
        lines: list[DialogueLine] = []
        with open(tsv_path, encoding="utf-8") as f:
            for row in f:
                row = row.strip()
                if not row:
                    continue
                parts = row.split("\t", 2)
                if len(parts) >= 2:
                    line_en = parts[2] if len(parts) == 3 else ""
                    lines.append(DialogueLine(speaker=parts[0], line=parts[1], line_en=line_en))
        return lines

    # ------------------------------------------------------------------ #
    #  Chunking
    # ------------------------------------------------------------------ #
    def _chunk_lines(
        self, lines: list[DialogueLine]
    ) -> list[list[DialogueLine]]:
        """バイト上限に収まるようセリフをチャンク分割する"""
        chunks: list[list[DialogueLine]] = []
        current: list[DialogueLine] = []
        current_bytes = 0

        for dl in lines:
            entry = f"{dl.speaker}: {dl.line}\n"
            size = len(entry.encode("utf-8"))
            if current and current_bytes + size > self.chunk_max_bytes:
                chunks.append(current)
                current = []
                current_bytes = 0
            current.append(dl)
            current_bytes += size

        if current:
            chunks.append(current)
        return chunks

    # ------------------------------------------------------------------ #
    #  Gemini TTS
    # ------------------------------------------------------------------ #
    def _build_speech_config(self) -> types.SpeechConfig:
        configs = [
            types.SpeakerVoiceConfig(
                speaker=speaker,
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice,
                    )
                ),
            )
            for speaker, voice in self.voices.items()
        ]
        return types.SpeechConfig(
            multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                speaker_voice_configs=configs,
            ),
        )

    def _generate_chunk(self, chunk: list[DialogueLine]) -> bytes:
        """1チャンク分の音声を生成し、PCM bytes を返す"""
        text = "\n".join(f"{dl.speaker}: {dl.line if self.main_locale == "ja" else dl.line_en }" for dl in chunk)

        use_director_prompt = self.director_prompt
        if type(self.director_prompt) is list:
          use_director_prompt = self.director_prompt[min(len(self.director_prompt) - 1, self.current_scene_index)]

        print(use_director_prompt)

        contents = f"""
            {use_director_prompt}

            {text}
            """
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=self._build_speech_config(),
        )

        response = call_with_retry(
            self.client.models.generate_content,
            model=self.model,
            contents=contents,
            config=config,
            max_retries=3,
            base_delay=3.0,
            retryable_exceptions=(GeminiServerError, ConnectionError, TimeoutError),
            cancel_event=self.cancel_event,
        )

        data = response.candidates[0].content.parts[0].inline_data.data
        # SDK は通常 bytes を返すが、文字列(base64)の場合もデコード
        if isinstance(data, str):
            data = base64.b64decode(data)
        return data

    # ------------------------------------------------------------------ #
    #  WAV 保存
    # ------------------------------------------------------------------ #
    @staticmethod
    def _save_wav(pcm: bytes, path: Path) -> Path:
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(24000)
            wf.writeframes(pcm)
        return path

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #
    def generate_scene_audio(
        self,
        lines: list[DialogueLine],
        filename: str
    ) -> Path:
        """DialogueLine リストから WAV ファイルを生成"""
        chunks = self._chunk_lines(lines)
        all_pcm = bytearray()

        for i, chunk in enumerate(chunks, 1):
            if self.cancel_event and self.cancel_event.is_set():
                raise PipelineCancelledError("Cancelled during TTS chunk generation")
            chars = sum(len(dl.line) for dl in chunk)
            print(f"    chunk {i}/{len(chunks)}  ({len(chunk)} 行 / {chars} 字)")
            pcm = self._generate_chunk(chunk)
            all_pcm.extend(pcm)

        path = self.output_dir / filename
        self._save_wav(bytes(all_pcm), path)
        return path

    def run(self, tsv_paths: list[Path]) -> list[Path]:
        """複数 TSV ファイルからシーンごとの WAV を生成"""
        wav_files: list[Path] = []

        for i, tsv_path in enumerate(tsv_paths):
            if self.cancel_event and self.cancel_event.is_set():
                raise PipelineCancelledError("Cancelled during TTS scene loop")
            print(f"\n  音声生成: {tsv_path.name}")
            lines = self.read_tsv(tsv_path)
            if not lines:
                print("    スキップ (セリフなし)")
                continue
            self.current_scene_index = i
            wav_name = tsv_path.stem + ".wav"
            wav_path = self.generate_scene_audio(lines, wav_name)
            wav_files.append(wav_path)
            print(f"    -> {wav_path}")

        # 全シーン結合
        # if len(wav_files) > 1:
        #     combined = self._combine_wavs(wav_files, "all_scenes.wav")
        #     print(f"\n  統合 WAV: {combined}")

        return wav_files

    def _combine_wavs(self, wav_paths: list[Path], filename: str) -> Path:
        """複数 WAV を単純結合"""
        all_pcm = bytearray()
        for p in wav_paths:
            with wave.open(str(p), "rb") as wf:
                all_pcm.extend(wf.readframes(wf.getnframes()))
        return self._save_wav(bytes(all_pcm), self.output_dir / filename)


if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    import os
    import tomllib
    load_dotenv()

    parser = argparse.ArgumentParser(description="Text to Speech (Gemini)")
    parser.add_argument("dir", type=Path, help="scene_*.tsvを含むディレクトリ")
    # parser.add_argument("voices", default="Vindemiatrixw,Zubenelgenubi", type=str, help="voice")
    args = parser.parse_args()

    tsv_files = sorted(args.dir.glob("scene_*.tsv"))
    # voices = args.voices.split(",")
    model = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-tts")
    chunk_max_bytes = int(os.getenv("GEMINI_TTS_MAX_CHUNK_BYTES", 5000))
    main_localel = "ja"
    dn = ""

    with open("./app_config.toml", "rb") as f:
      data = tomllib.load(f)
      if "directors_notes" in data:
        print("loading [directors_notes]..")
        dn = data["directors_notes"]
      if "main_locale" in data:
        print("loading [main_locale]..")
        main_locale = data["main_locale"]

      tts = TTSPipeline(
        output_dir=args.dir,
        model=model,
        # voices={
        #   "<ドローン>": voices[0],
        #   "<カタパルト>": voices[1]
        # },
        chunk_max_bytes=chunk_max_bytes,
        main_locale=main_locale,
        director_prompt=dn
      )

    result = tts.run(tsv_files)
    print(f"\n完了: {len(result)} ファイル")
