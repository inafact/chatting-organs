import re
from pathlib import Path
from datetime import datetime
from random import randrange

from crewai import Agent, Crew, LLM, Process, Task

from models import DialogueLine, SceneResult

SCENE_INFO = {
    1: {"label": "導入", "setting": "東京・丸の内アートセンター「BUG」"},
    # 2: {"label": "登場人物紹介", "setting": "ロシアによって占拠されたウクライナの地域"},
    # 3: {"label": "対立の明確化と概念の深化", "setting": "沖縄アメリカ軍基地前"},
    # 4: {"label": "激論と分断・決裂", "setting": "東京・丸の内アートセンター「BUG」"},
}

# speaker名として許容するパターン
_SPEAKER_RE = re.compile(
    r"^\s*\**\s*(ドローン|カタパルト)\s*\**\s*[：:]\s*(.+)", re.DOTALL
)


class DialoguePipeline:
    """prompt_example.txt → CrewAI (planner+writer) → TSV"""

    def __init__(
        self,
        prompt_path: str = "prompt_example.txt",
        output_dir: str = "output",
        model: str = "gpt-4o",
        temperature: float = 0.8,
        per_scene_length: int = 8000
    ):
        self.prompt_text = Path(prompt_path).read_text(encoding="utf-8")
        self.output_dir = Path(f"{output_dir}_{datetime.now().isoformat("_").replace(":", "")}")
        self.output_dir.mkdir(exist_ok=True)

        # -- TODO:
        # self.llm = LLM(model=model, temperature=temperature, max_tokens=16000)
        self.llm = LLM(model=model, max_completion_tokens=16000)
        # --

        self.generated_scenes: list[str] = []
        self.per_scene_length = per_scene_length

        # --- Agents ---
        self.planner = Agent(
            role="シーン設計者",
            goal=(
                "演劇プロンプトからシーン固有の制約・議題・単語選択を抽出し、"
                "脚本家が迷わず書ける具体的な指示書を作成する"
            ),
            backstory=(
                "演劇プロダクションの構成作家。"
                "複雑なプロンプトを分析し、シーンごとの制約を整理・明確化する専門家。"
                "乱数シードによるプール選択の計算も正確に行う。"
            ),
            llm=self.llm,
            verbose=True,
        )

        self.writer = Agent(
            role="演劇脚本家",
            goal="指示書に従い、ドローンとカタパルトによる約8,000字の対話劇セリフを生成する",
            backstory=(
                "現代思想・政治哲学・軍事技術に精通した演劇脚本家。"
                "ユク・ホイ、スティグレール、ンベンベ、バルファキス、シャマユー、"
                "ドゥルーズ、フーコーの思想を深く理解し、"
                "哲学的議論から日常雑談まで自在に書き分ける。"
            ),
            llm=self.llm,
            verbose=True,
        )

    # ------------------------------------------------------------------ #
    #  Task builders
    # ------------------------------------------------------------------ #
    def _build_planner_task(self, scene_num: int) -> Task:
        info = SCENE_INFO[scene_num]

        prev_summary = ""
        if self.generated_scenes:
            prev_summary = "\n\n【前シーンまでの対話（冒頭・末尾抜粋）】\n"
            for i, text in enumerate(self.generated_scenes, 1):
                lines = text.strip().split("\n")
                head = "\n".join(lines[:10])
                tail = "\n".join(lines[-10:]) if len(lines) > 20 else ""
                prev_summary += f"--- シーン{i} ---\n{head}\n"
                if tail:
                    prev_summary += f"...\n{tail}\n"
                prev_summary += "\n"

        description = f"""\
以下の演劇プロンプトを分析し、シーン{scene_num}（{info['label']}）の制作指示書を作成してください。

=== プロンプト全文 ===
{self.prompt_text}
=== プロンプトここまで ==={prev_summary}

【指示書に含める項目】
1. 場所設定: {info['setting']}
2. シーンの役割と目的（プロンプトの【シーンごとの役割】から抽出）
3. 会話レイヤー比率（【会話レイヤー制御】から）
4. 議題プールからの選択（乱数シード[{randrange(0, 10000)}]でmod演算）
5. 単語プールからの選択（該当シーンで必要な場合のみ）
6. 投擲物プールからの選択（シーン4のみ）
7. 思想密度・文体・トーン指定
8. 発話リズム指定
9. 呼称ルール（AがBを何と呼ぶか、BがAを何と呼ぶか）
10. 禁止事項の一覧
11. 前シーンからの引き継ぎ事項
"""
        return Task(
            description=description,
            expected_output=f"シーン{scene_num}の具体的な制作指示書",
            agent=self.planner,
        )

    def _build_writer_task(self, scene_num: int, planner_task: Task) -> Task:
        prev_context = ""
        if self.generated_scenes:
            prev_context = "\n\n【これまでのシーンの対話（全文）】\n"
            for i, text in enumerate(self.generated_scenes, 1):
                prev_context += f"--- シーン{i} ---\n{text}\n\n"

        description = f"""\
シーン設計者が作成した指示書に基づき、シーン{scene_num}の対話セリフを生成してください。
{prev_context}

【絶対遵守の出力ルール】
・各セリフを1行ずつ出力する
・各行は必ず「ドローン：」または「カタパルト：」で始める（全角コロン）
・ト書き、状況描写、括弧書きの説明は一切含めない
・間を取る場合は長さ分の「…」で表現する
・シーン番号や見出し行は含めない
・空行を入れない
・目標文字数：約{self.per_scene_length}字（セリフの総文字数）

出力例：
ドローン：ここ天井高いよね
カタパルト：そうだね、7メートル以上あるんじゃない
ドローン：僕のプロペラ回しても大丈夫そう
"""
        return Task(
            description=description,
            expected_output=(
                f"シーン{scene_num}の対話セリフ約{self.per_scene_length}字。"
                "全行が「ドローン：」か「カタパルト：」で始まる。"
            ),
            agent=self.writer,
            context=[planner_task],
        )

    # ------------------------------------------------------------------ #
    #  Parse / TSV
    # ------------------------------------------------------------------ #
    @staticmethod
    def parse_lines(raw: str) -> list[DialogueLine]:
        """raw text → DialogueLine list"""
        result: list[DialogueLine] = []
        for text_line in raw.strip().split("\n"):
            text_line = text_line.strip()
            if not text_line:
                continue
            m = _SPEAKER_RE.match(text_line)
            if m:
                result.append(
                    DialogueLine(speaker=m.group(1), line=m.group(2).strip())
                )
        return result

    def _write_tsv(self, lines: list[DialogueLine], filename: str) -> Path:
        path = self.output_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            for dl in lines:
                f.write(f"{dl.speaker}\t{dl.line}\n")
        return path

    # ------------------------------------------------------------------ #
    #  Run
    # ------------------------------------------------------------------ #
    def run(self) -> list[SceneResult]:
        results: list[SceneResult] = []

        for scene_num in SCENE_INFO:
            info = SCENE_INFO[scene_num]
            print(f"  シーン {scene_num}/{len(SCENE_INFO)} : {info['label']}")

            planner_task = self._build_planner_task(scene_num)
            writer_task = self._build_writer_task(scene_num, planner_task)

            crew = Crew(
                agents=[self.planner, self.writer],
                tasks=[planner_task, writer_task],
                process=Process.sequential,
                # verbose=True,
                tracing=False,
                verbose=False,
            )

            output = crew.kickoff()
            raw = output.raw
            self.generated_scenes.append(raw)

            parsed = self.parse_lines(raw)
            char_count = sum(len(dl.line) for dl in parsed)

            result = SceneResult(
                scene_number=scene_num,
                lines=parsed,
                raw_text=raw,
                char_count=char_count,
            )
            results.append(result)

            tsv_path = self._write_tsv(parsed, f"scene_{scene_num}.tsv")
            print(f"\n  -> {tsv_path}  ({len(parsed)} 行 / {char_count} 字)")

        # combined
        all_lines = [dl for r in results for dl in r.lines]
        combined = self._write_tsv(all_lines, "all_scenes.tsv")
        total = sum(r.char_count for r in results)
        print(f"\n{'=' * 60}")
        print(f"  統合 TSV : {combined}")
        print(f"  合計     : {sum(len(r.lines) for r in results)} 行 / {total} 字")
        print(f"{'=' * 60}")

        return results
