import os
from datetime import datetime

from dotenv import load_dotenv

from alignment import AlignmentPipeline
from pipeline import DialoguePipeline
from tts import TTSPipeline


def main():
    load_dotenv()

    print(f"start: {datetime.now()}")

    # --- 1. セリフ生成 (CrewAI + OpenAI) ---
    pipeline = DialoguePipeline(
        prompt_path="prompt_example.txt",
        # output_dir="output",
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        temperature=float(os.getenv("TEMPERATURE", "0.8")),
        per_scene_length=2500
    )

    results = pipeline.run()

    total = sum(r.char_count for r in results)
    print(f"\nセリフ生成完了: 全 {len(results)} シーン / 合計 {total} 字")
    print(f"next: {datetime.now()}")

    # --- 2. 音声生成 (Gemini TTS) ---
    dp = """
    - セリフの終わりや語尾に「！」の文字を含む場合は、口調を強めていき、「！」が2文字以上続く場合は最終的に怒ってがなるような口調にしてください。
    - セリフ間で間を十分にとってゆっくり話してください。「…」「、」「。」のいずれかの文字を含む場合もはっきりっと区切ってください。
    - セリフ内の（）の中に書かれている感情表現や間のとり方、読み方の指示にも従ってください。ただし、（）内を直接読み上げない事。
    """
    tts = TTSPipeline(
        output_dir=pipeline.output_dir,
        voices={"ドローン": "Kore", "カタパルト": "Enceladus"},
        model=os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-tts"),
        chunk_max_bytes=5000,
        director_prompt=dp
    )

    tsv_files = sorted(pipeline.output_dir.glob("scene_*.tsv"))
    wav_files = tts.run(tsv_files)

    print(f"\n音声生成完了: {len(wav_files)} ファイル")
    print(f"next: {datetime.now()}")

    # --- 3. Forced Alignment (ElevenLabs) ---
    aligner = AlignmentPipeline(
      output_dir=pipeline.output_dir,
      api_key=os.getenv("ELEVENLABS_API_KEY", None)
    )

    tsv_files = sorted(pipeline.output_dir.glob("scene_*.tsv"))
    wav_files = sorted(pipeline.output_dir.glob("scene_*.wav"))
    aligned_tsvs = aligner.run(tsv_files, wav_files)

    print(f"\nアライメント完了: {len(aligned_tsvs)} ファイル")
    print(f"finish: {datetime.now()}")

if __name__ == "__main__":
    main()
