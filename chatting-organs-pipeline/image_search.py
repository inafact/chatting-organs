import random
import warnings
from pathlib import Path
from threading import Event

import torch
from PIL import Image
import open_clip

from models import AlignedLine
from pipeline_utils import PipelineCancelledError, extract_scene_number

warnings.filterwarnings("ignore")

class ImageSearchPipeline:
    """Aligned TSV + images/ → OpenCLIP image search → 6-column TSV

    Each line_en is matched against pre-encoded images.
    If matches exceed the similarity threshold, one is randomly selected.
    """

    SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
    CHOICE_MODE = ["RANDOM", "RANDOM_N", "TOP", "TOP_N"]

    def __init__(
        self,
        output_dir: str | Path,
        images_dir: str | dict[int, str] | dict[str, str] = "images",
        model_name: str = "ViT-B-32",
        similarity_threshold: float = 0.2,
        search_src: str = "line_en",
        scenes_info: dict = dict(),
        cancel_event: Event | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.images_dir = images_dir
        self.similarity_threshold = similarity_threshold
        self.search_src = search_src
        self.cancel_event = cancel_event
        self.choice_mode = "TOP"
        self.choice_size = 1
        self.scenes_info = scenes_info

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[ImageSearch] デバイス: {self.device}")
        print(f"[ImageSearch] モデル読み込み中: {model_name}...")

        self.model, self.preprocess = open_clip.create_model_from_pretrained(
            model_name,
            pretrained=('openai' if model_name == "ViT-B-32" else "webli"),
            device=self.device
        )
        self.tokenizer = open_clip.get_tokenizer(model_name)
        self.model.eval()

        # --
        if type(self.images_dir) == str:
            self.image_features, self.image_paths = self._encode_all_images(self.images_dir)
            print(f"[ImageSearch] 準備完了 (画像 {len(self.image_paths)} 枚)")

    # ------------------------------------------------------------------ #
    #  画像の事前エンコード
    # ------------------------------------------------------------------ #
    def _encode_all_images(self, dir_paths: str) -> tuple[torch.Tensor | None, list[Path]]:
        _path = Path(dir_paths)

        if not _path.exists():
            print(f"[ImageSearch] 画像ディレクトリが見つかりません: {_path}")
            return None, []

        image_files = sorted(
            f for f in _path.iterdir()
            if f.is_file() and f.suffix.lower() in self.SUPPORTED_EXTENSIONS
        )

        if not image_files:
            print(f"[ImageSearch] 画像ファイルが見つかりません: {_path}")
            return None, []

        valid_images = []
        valid_paths = []

        for path in image_files:
            try:
                image = Image.open(path).convert("RGB")
                processed = self.preprocess(image).unsqueeze(0)
                valid_images.append(processed)
                valid_paths.append(path)
            except Exception as e:
                print(f"  スキップ: {path.name} ({e})")

        if not valid_images:
            return None, []

        images_tensor = torch.cat(valid_images).to(self.device)

        with torch.no_grad():
            features = self.model.encode_image(images_tensor)
            features = features / features.norm(dim=-1, keepdim=True)

        return features, valid_paths

    # ------------------------------------------------------------------ #
    #  テキスト → 画像マッチング
    # ------------------------------------------------------------------ #
    #
    # - TODO: improve
    #
    def _find_matching_image(self, search_line: str) -> str:
        if not search_line or self.image_features is None or len(self.image_paths) == 0:
            return ""

        text_tokens = self.tokenizer([search_line]).to(self.device)

        with torch.no_grad():
            text_features = self.model.encode_text(text_tokens)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)

        similarities = (self.image_features @ text_features.T).squeeze()

        if similarities.dim() == 0:
            similarities = similarities.unsqueeze(0)

        scores = similarities.cpu().numpy()

        matches = [
            self.image_paths[i]
            for i, s in enumerate(scores)
            if s >= self.similarity_threshold
        ]

        # print("-"*10)
        # print(search_line)
        # print(matches[:3])

        if matches:
          if self.choice_mode == "TOP":
            selected = matches[0:1]
          elif self.CHOICE_MODE == "TOP_N":
            selected = matches[0:self.choice_size]
          elif self.CHOICE_MODE == "RANDOM_N":
            selected = random.sample(matches, k=self.choice_size)
          else:
            selected = [random.choice(matches)]

          return ",".join(map(lambda s: str(s.resolve()), selected))

        return ""

    # ------------------------------------------------------------------ #
    #  TSV 読み書き
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
                    ))
        return lines

    @staticmethod
    def _write_aligned_tsv(aligned: list[AlignedLine], path: Path) -> Path:
        with open(path, "w", encoding="utf-8") as f:
            for al in aligned:
                f.write(
                    f"{al.speaker}\t{al.line}\t{al.line_en}\t{al.start_time:.3f}"
                    f"\t{al.stem_file_path}\t{al.reference_image_path}\n"
                )
        return path

    # ------------------------------------------------------------------ #
    #  Run
    # ------------------------------------------------------------------ #
    def run(self, aligned_tsv_paths: list[Path]) -> list[Path]:
        """Aligned TSV に reference_image_path 列を追加して上書き"""
        result_paths: list[Path] = []

        for tsv_path in aligned_tsv_paths:
            if self.cancel_event and self.cancel_event.is_set():
                raise PipelineCancelledError("Cancelled during image search")

            scene_num = extract_scene_number(tsv_path)

            if type(self.images_dir) == dict:
                print("-- dict mode --")
                if str(scene_num) in self.images_dir:
                    self.image_features, self.image_paths = self._encode_all_images(self.images_dir[str(scene_num)])
                    print(f"[ImageSearch] 準備完了 (画像 {len(self.image_paths)} 枚)")
                else:
                    self.image_features, self.image_paths = [None, []]
                    print("-- no reference (dict mode) --")

            print(f"\n  [ImageSearch] 処理中: {tsv_path.name}")
            lines = self.read_aligned_tsv(tsv_path)

            for al in lines:
                al.reference_image_path = self._find_matching_image(
                    al.line_en if self.search_src == "line_en" else al.line
                )
                if al.reference_image_path:
                    print(f"    {al.line_en[:40] if self.search_src == "line_en" else al.line[:40]}... -> {Path(al.reference_image_path).name}")

            self._write_aligned_tsv(lines, tsv_path)
            result_paths.append(tsv_path)
            print(f"    -> {tsv_path}  ({len(lines)} 行, 6列)")

        return result_paths


if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    import os
    import tomllib
    load_dotenv()

    image_search: dict = {
      "images_dir": "images",
      "model_name": "ViT-B-32",
      "similarity_threshold": 0.245,
      "search_src": "line_en"
    }
    scenes_info = dict()

    with open("./app_config.toml", "rb") as f:
        data = tomllib.load(f)
        if "render_scenes" in data:
            print("loading [render_scenes]..")
            scenes_info.update(data["render_scenes"])
        if "image_search" in data:
            print("loading [image_search]..")
            image_search.update(data["image_search"])
        print("loaded from app_config.yml..")
        print(scenes_info)
        print(image_search)

    parser = argparse.ArgumentParser(description="Image Search (OpenCLIP)")
    parser.add_argument("dir", type=Path, help="*_aligned.tsv を含むディレクトリ")
    if type(image_search["images_dir"]) == str:
        parser.add_argument("--images-dir", type=str, default=image_search["images_dir"])
    parser.add_argument("--model", type=str, default=image_search["model_name"])
    parser.add_argument("--threshold", type=float, default=image_search["similarity_threshold"])
    parser.add_argument("--search-src", type=str, default=image_search["search_src"], choices=["line_en", "line"])
    args = parser.parse_args()

    aligned_tsvs = sorted(args.dir.glob("*_aligned.tsv"))

    searcher = ImageSearchPipeline(
        output_dir=args.dir,
        images_dir=image_search["images_dir"] if type(image_search["images_dir"]) == dict else args.images_dir,
        model_name=args.model,
        similarity_threshold=args.threshold,
        search_src=args.search_src,
        scenes_info=scenes_info,
    )
    result = searcher.run(aligned_tsvs)
    print(f"\n完了: {len(result)} ファイル")
