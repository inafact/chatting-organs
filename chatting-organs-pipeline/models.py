from pydantic import BaseModel


class DialogueLine(BaseModel):
    """1行のセリフ"""
    speaker: str  # ドローン or カタパルト
    line: str
    line_en: str = ""


class AlignedLine(BaseModel):
    """タイムスタンプ付きセリフ"""
    speaker: str
    line: str
    line_en: str = ""
    start_time: float  # seconds
    stem_file_path: str
    reference_image_path: str = ""
    direction_sound: str = ""
    direction_lighting: str = ""
    direction_drone: str = ""
    direction_catapult: str = ""


class SceneResult(BaseModel):
    """1シーンの生成結果"""
    scene_number: int
    lines: list[DialogueLine]
    raw_text: str
    char_count: int
