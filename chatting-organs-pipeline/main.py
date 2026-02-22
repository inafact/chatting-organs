import os
import threading
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
from direction import DirectionPipeline
from image_search import ImageSearchPipeline
from pipeline import DialoguePipeline
from tts import TTSPipeline
from pipeline_utils import PipelineCancelledError

load_dotenv()

ip = os.environ.get("OSC_RECV_HOST", "0.0.0.0")
port = int(os.environ.get("OSC_RECV_PORT", '10000'))
dispatcher = Dispatcher()


class PipelineManager:
  def __init__(self, td_player_address: str = "0.0.0.0", td_player_port: int = 10001):
    self.pipeline_running = False
    self._cancel_event: threading.Event | None = None
    self._pipeline_thread: threading.Thread | None = None
    self._reply_client = None
    self.td_player_address = td_player_address
    self.td_player_port = td_player_port
    self.main_locale = "ja"
    # -- TODO:
    self.render_scenes = dict()
    self.directors_notes = []
    # --
    self.image_search_config = {
      "enabled": False,
      "images_dir": "images",
      "model_name": "ViT-B-32",
      "similarity_threshold": 0.245,
      "search_src": "line_en"
    }
    self.direction_config = {
      "enabled": False,
      "prompt_path": "direction_prompt_example.txt",
    }
    # -- TODO: move into tts.py
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
    SimpleUDPClient(client_address[0], 12001).send_message("/reply", 2)

  def reload_configs(self, client_address, address, *args):
    if len(args) == 1:
      ret = self._reload_configs(args[0])
    else:
      ret = self._reload_configs()
    SimpleUDPClient(client_address[0], 12001).send_message("/reply", ret)

  def _reload_configs(self, config_file: str | Path = "./app_config.toml") -> int:
    if type(config_file) is Path:
      if not config_file.exists():
        return - 1
    else:
      try:
        cf = Path(config_file)
        if not cf.exists():
          return -1
      except TypeError as e:
        return -1

    with open(str(config_file), "rb") as f:
      data = tomllib.load(f)
      if "directors_notes" in data:
        print("loading [directors_notes]..")
        self.directors_notes = data["directors_notes"]
      if "main_locale" in data:
        print("loading [main_locale]..")
        self.main_locale = data["main_locale"]
      if "render_scenes" in data:
        print("loading [render_scenes]..")
        self.render_scenes = dict()
        # -- NOTE: tomllib might convert int-based keys into to str-based keys
        self.render_scenes.update(data["render_scenes"])
      if "image_search" in data:
        print("loading [image_search]..")
        # -- NOTE: tomllib might convert int-based keys into to str-based keys
        self.image_search_config.update(data["image_search"])
      if "direction" in data:
        print("loading [direction]..")
        self.direction_config.update(data["direction"])
    print(self.render_scenes)
    print(self.directors_notes)
    print(self.image_search_config)
    print(self.direction_config)
    print(self.main_locale)

    return 3

  def run_pipeline(self, client_address, address, *args):
    if len(args) == 1:
      voices = [
        args[0],
        choice(
          list(filter(lambda k: k != args[0], self.voices_gemini.keys()))
        )
      ]
    elif len(args) > 1:
      voices = list(args)
    else:
      voices = ["Vindemiatrix", "Zubenelgenubi"]

    # -- TODO:
    if self.pipeline_running:
      print("pipeline is running..")
      return

    self._reply_client = client_address
    self._cancel_event = threading.Event()
    self.pipeline_running = True

    self._pipeline_thread = threading.Thread(
      target=self._run_pipeline_thread,
      args=(voices,),
      daemon=True,
    )
    self._pipeline_thread.start()

  def _run_pipeline_thread(self, voices):
    """バックグラウンドスレッドで実行。エラー・キャンセルを捕捉する。"""
    try:
      # -- TODO:
      paths = self._run_pipeline(voices)
      SimpleUDPClient(self.td_player_address, self.td_player_port).send_message(
        "/pipeline_finished", paths
      )
      SimpleUDPClient(self._reply_client[0], 12001).send_message("/reply", 1)
      # --
    except PipelineCancelledError:
      print(f"[PIPELINE CANCELLED] @{datetime.now()}")
      SimpleUDPClient(self._reply_client[0], 12001).send_message("/reply", -2)
    except Exception as e:
      print(f"[PIPELINE ERROR] {e} @{datetime.now()}")
      SimpleUDPClient(self._reply_client[0], 12001).send_message("/reply", -1)
    finally:
      self.pipeline_running = False
      self._cancel_event = None

  def cancel_pipeline(self, client_address, address, *args):
    if self.pipeline_running and self._cancel_event is not None:
      self._cancel_event.set()
      print("[CANCEL REQUESTED]")
      SimpleUDPClient(client_address[0], 12001).send_message("/reply", 4)
    else:
      print("No pipeline running to cancel")
      SimpleUDPClient(client_address[0], 12001).send_message("/reply", 0)

  def _run_pipeline(self, voices = ["Vindemiatrix", "Zubenelgenubi"]) -> list:
    print(f"[PIPELINE STARTED] @{datetime.now()}")

    #": " --- 1. セリフ生成 (CrewAI + Gemini or OpenAI)": " ---
    pipeline = DialoguePipeline(
        prompt_path="prompt_example.txt",
        # output_dir="output",
        model=os.getenv("GEMINI_LLM_MODEL", "gpt-4o"),
        temperature=float(os.getenv("TEMPERATURE", "0.8")),
        render_scenes=self.render_scenes,
        cancel_event=self._cancel_event,
    )

    results = pipeline.run()

    total = sum(r.char_count for r in results)
    print(f"\nセリフ生成完了: 全 {len(results)} シーン / 合計 {total} 字")
    print(f"@{datetime.now()}")

    #": " --- 2. 音声生成 (Gemini TTS)": " ---
    if self._cancel_event and self._cancel_event.is_set():
      raise PipelineCancelledError("Cancelled before TTS")

    tts = TTSPipeline(
        output_dir=pipeline.output_dir,
        voices={ "<ドローン>": voices[0], "<カタパルト>": voices[1] },
        model=os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-tts"),
        chunk_max_bytes=int(os.getenv("GEMINI_TTS_MAX_CHUNK_BYTES", 5000)),
        director_prompt=self.directors_notes,
        main_locale=self.main_locale,
        cancel_event=self._cancel_event,
    )

    tsv_files = sorted(pipeline.output_dir.glob("scene_*.tsv"))
    wav_files = tts.run(tsv_files)

    print(f"\n音声生成完了: {len(wav_files)} ファイル")
    print(f"@{datetime.now()}")

    #": " --- 3. Forced Alignment (ElevenLabs)": " ---
    if self._cancel_event and self._cancel_event.is_set():
      raise PipelineCancelledError("Cancelled before Alignment")

    aligner = AlignmentPipeline(
      output_dir=pipeline.output_dir,
      api_key=os.getenv("ELEVENLABS_API_KEY", None),
      main_locale=self.main_locale,
      cancel_event=self._cancel_event,
    )

    tsv_files = sorted(pipeline.output_dir.glob("scene_*.tsv"))
    wav_files = sorted(pipeline.output_dir.glob("scene_*.wav"))
    aligned_tsvs = aligner.run(tsv_files, wav_files)

    print(f"\nアライメント完了: {len(aligned_tsvs)} ファイル")
    print(f"@{datetime.now()}")

    #": " --- 4. 画像検索 (OpenCLIP)": " ---
    if self._cancel_event and self._cancel_event.is_set():
      raise PipelineCancelledError("Cancelled before ImageSearch")

    if self.image_search_config.get("enabled", False):
      image_search = ImageSearchPipeline(
        output_dir=pipeline.output_dir,
        images_dir=self.image_search_config.get("images_dir", "images"),
        model_name=str(self.image_search_config.get("model_name", "ViT-B-32")),
        similarity_threshold=float(self.image_search_config.get("similarity_threshold", 0.2)),
        search_src=str(self.image_search_config.get("search_src", "line_en")),
        scenes_info=self.render_scenes,
        cancel_event=self._cancel_event,
      )
      aligned_tsvs = image_search.run(aligned_tsvs)
      print(f"\n画像検索完了: {len(aligned_tsvs)} ファイル")

    #": " --- 5. 演出指示生成 (DirectionPipeline)": " ---
    if self._cancel_event and self._cancel_event.is_set():
      raise PipelineCancelledError("Cancelled before Direction")

    if self.direction_config.get("enabled", False):
      direction_pipeline = DirectionPipeline(
        output_dir=pipeline.output_dir,
        prompt_path=str(self.direction_config.get("prompt_path", "direction_prompt_example.txt")),
        model=os.getenv("GEMINI_LLM_MODEL", "gpt-4o"),
        scenes_info=self.render_scenes,
        cancel_event=self._cancel_event,
      )
      aligned_tsvs = direction_pipeline.run(aligned_tsvs)
      print(f"\n演出指示生成完了: {len(aligned_tsvs)} ファイル")
      print(f"@{datetime.now()}")

    ret_first_tsv = Path(aligned_tsvs[-1]).resolve()
    print(f"[PIPELINE FINISHED] @{datetime.now()}")

    return [ str(pipeline.output_dir) ]

# ======================
# Initialize
# ======================

manager = PipelineManager(
  td_player_address = os.getenv("PLAYER_OSC_ADDR", "127.0.0.1"),
  td_player_port = int(os.getenv("PLAYER_OSC_PORT", 10001))
)

dispatcher.map("/run_pipeline", manager.run_pipeline, needs_reply_address=True)
dispatcher.map("/cancel_pipeline", manager.cancel_pipeline, needs_reply_address=True)
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
