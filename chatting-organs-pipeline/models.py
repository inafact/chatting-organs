from pydantic import BaseModel


class DialogueLine(BaseModel):
    """1行のセリフ"""
    speaker: str  # ドローン or カタパルト
    line: str


class AlignedLine(BaseModel):
    """タイムスタンプ付きセリフ"""
    speaker: str
    line: str
    start_time: float  # seconds


class SceneResult(BaseModel):
    """1シーンの生成結果"""
    scene_number: int
    lines: list[DialogueLine]
    raw_text: str
    char_count: int
