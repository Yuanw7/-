"""基于智谱 AI GLM-4.6V 的房间视觉分析模块。

本模块的核心设计原则：即使模型输出了"一万字思考过程 + 解释说明"，
强力解析器（Powerful Parser）也能从混乱文本中精准提取 JSON。
"""

from __future__ import annotations

import base64
import json
import os
import re as _re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from zhipuai import ZhipuAI

from cn_regulation_rules import CHINESE_REGULATION_SYSTEM_RULES
from models import RoomScene


MODEL_VISION = "glm-4.6V"

# ════════════════════════════════════════════════════════════════════════════════
# PROMPT 边界化 — 要求模型将 JSON 包裹在 <result></result> XML 标签中
# ════════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = "你是一个专业的房间场景分析助手。请直接分析用户提供的图片，不要输出与图片分析无关的内容。"

QUALITY_PROMPT = "这张图片是室内房间场景吗？图片质量能看清大致布局吗？请用JSON格式回复：{\"is_room\": true或false, \"is_blurry_or_unusable\": true或false, \"reason\": \"原因\"}"

SCENE_PROMPT = """分析这张房间照片，识别所有可见家具，给出位置和尺寸。

【输出格式】
将结果包裹在 <result></result> XML 标签之间，禁止输出任何说明文字：
<result>
{
  "room": {
    "boundary": {
      "walls": ["看到的墙面"],
      "windows": ["看到的窗户"],
      "doors": ["看到的门"]
    },
    "furniture": [
      {
        "name": "物品名称",
        "dimensions": {"width": 1.5, "depth": 0.8, "height": 0.9},
        "position": {"x": 0.5, "y": 1.2, "z": 0, "rotation_degrees": 0},
        "material": "材质"
      }
    ]
  }
}
</result>

【估算原则】
- 成年人身高约1.7m，以此估算家具高度
- 客厅沙发约1.8×0.85×0.9m，餐桌约1.2×0.7×0.75m
- 坐标单位：米；原点(0,0)在房间俯视图左下角，X轴向右，Y轴向上
"""


# ════════════════════════════════════════════════════════════════════════════════
# 强力解析器（Powerful Parser）— 从任何混乱输出中提取 JSON
# ════════════════════════════════════════════════════════════════════════════════

class _ImageQualityResult(BaseModel):
    is_room: bool
    is_blurry_or_unusable: bool
    reason: str


def extract_json_from_thinking_model(raw_text: str) -> dict[str, Any]:
    """从 Thinking Model 的混乱输出中精准提取 JSON。

    解析策略（按优先级依次尝试）：

    1. 精确匹配 <result>...</result> XML 标签（最高优先级）
    2. 去掉 ```json ``` markdown 代码块包裹
    3. 去掉 ``` ``` 普通代码块包裹
    4. 找到第一个 { 和最后一个 } 之间的内容
    5. 逐字符深度解析：从第一个 { 开始，用栈匹配闭合 }

    Args:
        raw_text: 模型返回的原始文本（可能包含思考过程、解释等）

    Returns:
        解析出的 Python dict

    Raises:
        ValueError: 所有策略均失败时抛出，包含错误详情和原始文本预览
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("模型返回了空文本，无法提取 JSON。")

    candidates: list[str] = []
    errors: list[str] = []

    def _try_parse(text: str, label: str) -> dict[str, Any] | None:
        """尝试将 text 解析为 JSON dict。失败返回 None。"""
        if not text or not text.strip():
            return None
        # 清理常见污染字符
        cleaned = text.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            errors.append(f"[{label}] json.loads 失败: {exc}")
            return None

    # ── 策略 1: XML 标签 <result>...</result> ────────────────────────────────
    xml_match = _re.search(
        r'<result[^>]*>(.*?)</result>',
        raw_text,
        _re.DOTALL | _re.IGNORECASE,
    )
    if xml_match:
        candidate = xml_match.group(1).strip()
        result = _try_parse(candidate, "XML标签")
        if result is not None:
            return result
        candidates.append(f"XML标签内容前200字符: {candidate[:200]!r}")

    # ── 策略 2: 去掉 ```json 代码块 ─────────────────────────────────────────
    lines = raw_text.strip().split("\n")
    # 找到 ```json 开始行和 ``` 结束行之间
    in_block = False
    block_lines: list[str] = []
    block_start = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```json") and not in_block:
            in_block = True
            block_start = i
            # 跳过 ```json 这一行，内容从下一行开始
            continue
        if stripped == "```" and in_block:
            in_block = False
            block_text = "\n".join(block_lines)
            result = _try_parse(block_text, "```json块")
            if result is not None:
                return result
            candidates.append(f"```json块内容前200字符: {block_text[:200]!r}")
            block_lines = []
        if in_block:
            block_lines.append(line)
    if in_block and block_lines:
        block_text = "\n".join(block_lines)
        result = _try_parse(block_text, "```json块(未关闭)")
        if result is not None:
            return result

    # ── 策略 3: 去掉普通 ``` 代码块 ────────────────────────────────────────
    in_block2 = False
    block2_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") and not in_block2:
            in_block2 = True
            continue
        if stripped == "```" and in_block2:
            in_block2 = False
            block_text = "\n".join(block2_lines)
            result = _try_parse(block_text, "```块")
            if result is not None:
                return result
            candidates.append(f"```块内容前200字符: {block_text[:200]!r}")
            block2_lines = []
        if in_block2:
            block2_lines.append(line)
    if in_block2 and block2_lines:
        block_text = "\n".join(block2_lines)
        result = _try_parse(block_text, "```块(未关闭)")
        if result is not None:
            return result

    # ── 策略 4: 第一个 { 到最后一个 } ───────────────────────────────────────
    stripped = raw_text.strip()
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = stripped[first_brace : last_brace + 1]
        result = _try_parse(candidate, "首{末}")
        if result is not None:
            return result
        candidates.append(f"首{{末}}内容前200字符: {candidate[:200]!r}")

    # ── 策略 5: 逐字符栈解析（最保守，解析任意嵌套 JSON） ─────────────────
    # 从第一个 { 开始，用栈匹配最外层 }
    start = stripped.find("{")
    if start != -1:
        depth = 0
        in_str = False
        escape_next = False
        last_valid = None
        for i, ch in enumerate(stripped[start:], start):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = stripped[start : i + 1]
                    result = _try_parse(candidate, "栈解析")
                    if result is not None:
                        return result
                    last_valid = candidate  # 记录最后一个近似有效片段

        if last_valid:
            candidates.append(f"栈解析最近候选前200字符: {last_valid[:200]!r}")

    # 所有策略均失败 → 抛出带完整上下文的异常
    all_errors = "\n".join(errors) if errors else "(无)"
    all_candidates = "\n\n".join(candidates) if candidates else "(无候选)"
    raise ValueError(
        f"所有解析策略均失败。\n"
        f"原始文本前500字符：{raw_text[:500]!r}\n\n"
        f"解析错误：\n{all_errors}\n\n"
        f"候选片段：\n{all_candidates}"
    )


# ════════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ════════════════════════════════════════════════════════════════════════════════

def _load_image_base64(image_path: str) -> str:
    """加载图片并返回 base64 编码字符串（不含 data URI 前缀）。"""
    path = Path(image_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"图片文件不存在: {path}")
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _create_client() -> ZhipuAI:
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key:
        raise EnvironmentError("ZHIPUAI_API_KEY 未设置。")
    return ZhipuAI(api_key=api_key)


def _normalize_room_scene_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """将模型返回的 JSON 规范化为 RoomScene schema 格式。"""
    room_like = payload.get("room") if isinstance(payload.get("room"), dict) else payload
    boundary_in = room_like.get("boundary", {}) if isinstance(room_like, dict) else {}
    furniture_in = room_like.get("furniture", []) if isinstance(room_like, dict) else []

    def _ensure_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _coerce_float(value: Any, default: float) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = (
                value.strip()
                .lower()
                .replace("m", "")
                .replace("米", "")
                .replace("厘米", "0.01")
                .replace("cm", "0.01")
                .strip()
            )
            try:
                return float(cleaned)
            except ValueError:
                return default
        if isinstance(value, dict):
            for key in ("value", "amount", "meters", "meter", "m", "estimate"):
                if key in value:
                    return _coerce_float(value[key], default)
        return default

    normalized_furniture = []
    for item in furniture_in if isinstance(furniture_in, list) else []:
        if not isinstance(item, dict):
            continue
        dims = item.get("dimensions", {}) if isinstance(item.get("dimensions"), dict) else {}
        pos = item.get("position", {}) if isinstance(item.get("position"), dict) else {}
        normalized_furniture.append(
            {
                "name": str(
                    item.get("name")
                    or item.get("className")
                    or item.get("description")
                    or "未知物品"
                ),
                "material": str(item.get("material") or "未知材质"),
                "dimensions": {
                    "width": _coerce_float(dims.get("width", 0.1), 0.1),
                    "depth": _coerce_float(dims.get("depth", 0.1), 0.1),
                    "height": _coerce_float(dims.get("height", 0.1), 0.1),
                },
                "position": {
                    "x": _coerce_float(pos.get("x", 0.0), 0.0),
                    "y": _coerce_float(pos.get("y", 0.0), 0.0),
                    "z": _coerce_float(pos.get("z", 0.0), 0.0),
                    "rotation_degrees": _coerce_float(
                        pos.get("rotation_degrees", item.get("rotation", 0.0)), 0.0
                    ),
                },
            }
        )

    return {
        "furniture": normalized_furniture,
        "boundary": {
            "walls": _ensure_list(boundary_in.get("walls")),
            "windows": _ensure_list(boundary_in.get("windows")),
            "doors": _ensure_list(boundary_in.get("doors")),
        },
    }


# ════════════════════════════════════════════════════════════════════════════════
# Core API
# ════════════════════════════════════════════════════════════════════════════════

def _call_glm_vision(
    client: ZhipuAI,
    image_base64: str,
    prompt: str,
    system_instruction: str,
) -> str:
    """向 GLM-4.6V 发送图片+文本，返回模型响应的文本内容。"""
    data_uri = f"data:image/jpeg;base64,{image_base64}"

    kwargs: dict[str, Any] = {
        "model": MODEL_VISION,
        "messages": [
            {"role": "system", "content": system_instruction},
            {
                "role": "user",
                "content": [
                    # 官方文档要求：text 在前，image_url 在后
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
    }

    response = client.chat.completions.create(**kwargs)

    # 安全提取 content：message.content 可能是 str | list | None
    raw_msg = response.choices[0].message
    if isinstance(raw_msg.content, list):
        parts = []
        for part in raw_msg.content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif part.get("type") == "image_url":
                    parts.append("[图片]")
        content = "".join(parts)
    else:
        content = raw_msg.content

    if not content:
        raise RuntimeError(
            f"GLM-4.6V 返回了空内容。model={MODEL_VISION}，"
            f"raw_response={response.model_dump()}"
        )
    return content


def analyze_room_image(image_path: str) -> RoomScene:
    """分析房间照片，返回结构化的 RoomScene 对象。

    使用强力解析器（extract_json_from_thinking_model）从 Thinking Model
    的混乱输出中精准提取 JSON，保证任何情况下都能尽可能解析成功。

    Args:
        image_path: 图片文件路径（本地路径或绝对路径）

    Raises:
        FileNotFoundError: 图片文件不存在
        ValueError: 图片非房间场景或质量不合格
        RuntimeError: 所有解析策略均失败
    """
    client = _create_client()
    image_b64 = _load_image_base64(image_path)

    # ── 步骤 1: 图片质量检测 ────────────────────────────────────────────────
    quality_text = _call_glm_vision(
        client,
        image_b64,
        QUALITY_PROMPT,
        "你是图片质量评估专家。将结果包裹在 <result></result> 标签之间，禁止输出任何解释。",
    )

    try:
        quality_payload: dict[str, Any] = extract_json_from_thinking_model(quality_text)
        quality = _ImageQualityResult.model_validate(quality_payload)
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(
            f"无法解析图片质量评估结果（强力解析器）：{exc}"
        ) from exc

    if not quality.is_room:
        raise ValueError(f"图片未识别为室内房间场景：{quality.reason}")
    if quality.is_blurry_or_unusable:
        raise ValueError(f"图片质量不合格（模糊/遮挡/光线过暗）：{quality.reason}")

    # ── 步骤 2: 场景提取 ───────────────────────────────────────────────────
    scene_text = _call_glm_vision(
        client,
        image_b64,
        SCENE_PROMPT,
        SYSTEM_PROMPT,
    )

    try:
        scene_payload = extract_json_from_thinking_model(scene_text)
        normalized_payload = _normalize_room_scene_payload(scene_payload)
        return RoomScene.model_validate(normalized_payload)
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(
            f"无法从 GLM-4.6V 响应中提取 RoomScene JSON（强力解析器）：{exc}"
        ) from exc
