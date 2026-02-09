import os
from pathlib import Path
from datetime import datetime
import asyncio
from random import sample, choice
import tomllib

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
    self.directors_notes = []
    self.render_scenes = dict()
    # -- TODO:
    self.voices_gemini = {
      "Zephyr": "Bright"
      , "Puck": "Upbeat"
      , "Charon": "情報が豊富"
      , "Kore": "Firm"
      , "Fenrir": "Excitable"
      , "Leda": "Youthful"
      , "Orus": "Firm"
      , "Aoede": "Breezy"
      , "Callirrhoe": "のんびり屋"
      , "Autonoe": "Bright"
      , "Enceladus": "Breathy"
      , "Iapetus": "Clear"
      , "Umbriel": "Easy-going"
      , "Algieba": "Smooth"
      , "Despina": "Smooth"
      , "Erinome": "クリア"
      , "Algenib": "Gravelly"
      , "Rasalgethi": "情報が豊富"
      , "Laomedeia": "アップビート"
      , "Achernar": "Soft"
      , "Alnilam": "Firm"
      , "Schedar": "Even"
      , "Gacrux": "成人向け"
      , "Pulcherrima": "転送"
      , "Achird": "フレンドリー"
      , "Zubenelgenubi": "カジュアル"
      , "Vindemiatrix": "Gentle"
      , "Sadachbia": "Lively"
      , "Sadaltager": "知識が豊富"
      , "Sulafat": "Warm"
    }
    # --
    self._reload_configs()

  def reload_env(self, client_address, address, *args):
    load_dotenv()
    SimpleUDPClient(client_address[0], 12001).send_message("/reply", 1)

  def reload_configs(self, client_address, address, *args):
    print(args)
    self._reload_configs()
    SimpleUDPClient(client_address[0], 12001).send_message("/reply", 1)

  def _reload_configs(self):
    with open("./app_config.toml", "rb") as f:
      data = tomllib.load(f)
      if "directors_notes" in data:
        print("loading [directors_notes]..")
        self.directors_notes = data["directors_notes"]
      if "render_scenes" in data:
        print("loading [render_scenes]..")
        for k, el in enumerate(data["render_scenes"]):
          self.render_scenes[int(el)] = data["render_scenes"][el]
    print(self.render_scenes)
    print(self.directors_notes)

  def run_pipeline(self, client_address, address, *args):
    paths: list

    if len(args) == 1:
      voices = [
        args[0],
        choice(
          list(filter(lambda k: k != args[0], self.voices_gemini.keys()))
        )
      ]
      paths = self._run_pipeline()
    elif len(args) > 1:
      paths = self._run_pipeline(voices=args)
    else:
      paths = self._run_pipeline()

    SimpleUDPClient(self.player_address, self.player_port).send_message(
      "/load_files", paths
    )
    SimpleUDPClient(client_address[0], 12001).send_message("/reply", 1)

  def _run_pipeline(self, voices = ["Kore",  "Enceladus"]) -> list:
    if self.pipeline_running:
      print("pipline is running..")
      return []
    if len(voices) < 2:
      print("error")
      return []

    print(f"use voices: {voices[0]}, {voices[1]}")
    print(f"start: {datetime.now()}")
    self.pipeline_running = True

    #": " --- 1. セリフ生成 (CrewAI + OpenAI)": " ---
    pipeline = DialoguePipeline(
        prompt_path="prompt_example.txt",
        # output_dir="output",
        # model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        model=os.getenv("GEMINI_LLM_MODEL", "gpt-4o"),
        temperature=float(os.getenv("TEMPERATURE", "0.8")),
        per_scene_length=self.render_scenes
    )

    results = pipeline.run()

    total = sum(r.char_count for r in results)
    print(f"\nセリフ生成完了: 全 {len(results)} シーン / 合計 {total} 字")
    print(f"next: {datetime.now()}")

    #": " --- 2. 音声生成 (Gemini TTS)": " ---
    # dp = [
    #   """
    #   ### DIRECTOR'S NOTES

    #   Pacing: Speaks at an energetic pace, keeping up with the extremely fast, rapid
    #   """,
    #   """
    #   ### DIRECTOR'S NOTES FOR ドローン

    #   Character: Old woman
    #   Pacing: Speaks at an energetic pace, keeping up with the extremely fast, rapid

    #   ### DIRECTOR'S NOTES FOR カタパルト

    #   Character: Young man, high-tone voice
    #   Pacing: Speaks at an exhausted pace, keeping up with the extremely slow
    #   """,
    #   """
    #   ### DIRECTOR'S NOTES FOR ドローン

    #   Pacing: Speaks at an energetic pace, keeping up with the extremely fast and angry

    #   ### DIRECTOR'S NOTES FOR カタパルト

    #   Pacing: Speaks at an energetic pace, keeping up with the extremely fast and angry
    #   """,

    #   """
    #   - 全体的に興奮した調子で読み上げてください。
    #   - セリフの終わりや語尾に「！」の文字を含む場合は、口調を強めていき、「！」が2文字以上続く場合は最終的に怒ってがなるような口調にしてください。
    #   - セリフ間で間を十分にとってゆっくり話してください。「…」「、」「。」のいずれかの文字を含む場合もはっきりっと区切ってください。
    #   """
    # ]

    tts = TTSPipeline(
        output_dir=pipeline.output_dir,
        voices={
          "ドローン": voices[0],
          "カタパルト": voices[1]
        },
        model=os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-tts"),
        chunk_max_bytes=5000,
        director_prompt=self.directors_notes
    )

    tsv_files = sorted(pipeline.output_dir.glob("scene_*.tsv"))
    wav_files = tts.run(tsv_files)

    print(f"\n音声生成完了: {len(wav_files)} ファイル")
    print(f"next: {datetime.now()}")

    #": " --- 3. Forced Alignment (ElevenLabs)": " ---
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
    self.pipeline_running = False
    return [
      str(Path(wav_files[-1]).resolve()),
      str(Path(aligned_tsvs[-1]).resolve())
    ]

# ======================
# Initialize
# ======================

manager = PipelineManager(
  player_address = os.getenv("PLAYER_OSC_ADDR", "127.0.0.1"),
  player_port = int(os.getenv("PLAYER_OSC_PORT", 10001))
)

dispatcher.map("/run_pipeline", manager.run_pipeline, needs_reply_address=True)
dispatcher.map("/reload_env", manager.reload_env, needs_reply_address=True)
dispatcher.map("/reload_configs", manager.reload_configs, needs_reply_address=True)


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
