import os
from pathlib import Path
from datetime import datetime
import asyncio

from dotenv import load_dotenv

from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.dispatcher import Dispatcher
from pythonosc.udp_client import SimpleUDPClient

from alignment import AlignmentPipeline
from pipeline import DialoguePipeline
from tts import TTSPipeline

load_dotenv()

ip = os.environ.get("OSC_RECV_HOST", "0.0.0.0")
port = int(os.environ.get("OSC_RECV_PORT", '12000'))
dispatcher = Dispatcher()


class PipelineManager:
  def __init__(self, player_address: str = "0.0.0.0", player_port: int = 10001):
    self.pipeline_running = False
    self.player_address = player_address
    self.player_port = player_port

  def run_pipeline(self, client_address, address, *args):
    if self.pipeline_running:
      print("pipline is running..")
      return

    print(f"start: {datetime.now()}")
    self.pipeline_running = True

    # --- 1. セリフ生成 (CrewAI + OpenAI) ---
    pipeline = DialoguePipeline(
        prompt_path="prompt_example.txt",
        # output_dir="output",
        # model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        model=os.getenv("GEMINI_LLM_MODEL", "gpt-4o"),
        temperature=float(os.getenv("TEMPERATURE", "0.8")),
        per_scene_length={ 1: 1000, 2: 2000, 3: 2000, 4: 1500 }
    )

    results = pipeline.run()

    total = sum(r.char_count for r in results)
    print(f"\nセリフ生成完了: 全 {len(results)} シーン / 合計 {total} 字")
    print(f"next: {datetime.now()}")

    # --- 2. 音声生成 (Gemini TTS) ---
    dp = [
      """
      ### DIRECTOR'S NOTES

      Pacing: Speaks at an energetic pace, keeping up with the extremely fast, rapid
      """,
      """
      ### DIRECTOR'S NOTES FOR ドローン

      Pacing: Speaks at an energetic pace, keeping up with the extremely fast, rapid

      ### DIRECTOR'S NOTES FOR カタパルト

      Pacing: Speaks at an exhausted pace, keeping up with the extremely slow
      """,
      """
      ### DIRECTOR'S NOTES FOR ドローン

      Pacing: Speaks at an energetic pace, keeping up with the extremely fast and angry

      ### DIRECTOR'S NOTES FOR カタパルト

      Pacing: Speaks at an energetic pace, keeping up with the extremely fast and angry
      """,

      """
      - 全体的に興奮した調子で読み上げてください。
      - セリフの終わりや語尾に「！」の文字を含む場合は、口調を強めていき、「！」が2文字以上続く場合は最終的に怒ってがなるような口調にしてください。
      - セリフ間で間を十分にとってゆっくり話してください。「…」「、」「。」のいずれかの文字を含む場合もはっきりっと区切ってください。
      """
    ]

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

    # TODO: error statte
    print(Path(aligned_tsvs[-1]).resolve(), Path(wav_files[-1]).resolve())
    SimpleUDPClient(self.player_address, self.player_port).send_message(
      "/load_files", [
        str(Path(wav_files[-1]).resolve()),
        str(Path(aligned_tsvs[-1]).resolve())
      ]
    )
    # TODO: error statte
    SimpleUDPClient(client_address[0], 12001).send_message("/reply", 1)
    self.pipeline_running = False

manager = PipelineManager(
  player_address = os.getenv("PLAYER_OSC_ADDR", "127.0.0.1"),
  player_port = int(os.getenv("PLAYER_OSC_PORT", 10001))
)
dispatcher.map("/run_pipeline", manager.run_pipeline, needs_reply_address=True)

async def loop():
  try:
    while True:
      await asyncio.sleep(1/60)
  except KeyboardInterrupt:
    pass


async def main():
  server = AsyncIOOSCUDPServer((ip, port), dispatcher, asyncio.get_event_loop())
  transport, protocol = (await server.create_serve_endpoint())
  await loop()
  transport.close()


if __name__ == "__main__":
  asyncio.run(main())
