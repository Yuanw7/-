"""Blueprint Vision Engine — 2D 归一化中心点坐标系分析模块。

本模块基于几何中心点坐标系，从房间图像中提取空间信息并生成标准化蓝图。

坐标系统：
- 原点 (0, 0) 位于房间左下角（俯视图）
- X 轴正向：向右
- Y 轴正向：向上
- 所有尺寸单位：毫米 (mm)
- 位置：物体几何中心点坐标
"""

from __future__ import annotations

import base64
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from zhipuai import ZhipuAI

from models import (
    BlueprintAdjacency,
    BlueprintBoundary,
    BlueprintDimensions,
    BlueprintFurniture,
    BlueprintPosition,
    RoomBlueprint,
)


MODEL_VISION = "glm-4.6v"


# ════════════════════════════════════════════════════════════════════════════════
# System Prompts
# ════════════════════════════════════════════════════════════════════════════════

BLUEPRINT_ANALYSIS_PROMPT = """【角色】资深建筑测绘工程师

【任务】识别输入图像中的空间边界与家具，建立 2D 归一化中心点坐标系。

【思维链 (Chain-of-Thought)】

第一步：边界识别
- 寻找地面与墙面的交线（墙角线）
- 确定房间的四个边界点
- 设定房间二维原点 (0,0) 为左下角
- 测量房间总宽度和总深度（单位：毫米）

第二步：对象提取
- 遍历所有可见家具
- 提取每个家具的边界盒（包围盒）
- 估算家具的宽度、深度、高度（单位：毫米）

第三步：坐标转换
- 计算每个家具的几何中心点坐标 (x, y)
- 几何中心 = (左边界 + 宽度/2, 下边界 + 深度/2)
- 记录旋转角度（顺时针，正值）

第四步：拓扑初建
- 记录主要家具之间的相邻关系
- 标记主要通道障碍物

【约束】
- 坐标必须基于物体的【几何中心点】
- 尺寸单位统一为毫米 (mm)
- 原点 (0, 0) 位于房间左下角
- 仅输出符合 Pydantic `RoomBlueprint` 格式的 JSON，禁止解释
- 家具 ID 使用简洁的英文或数字组合（如 sofa_1, table_1）

【输出格式】将结果包裹在 <result></result> XML 标签之间：

<result>
{{
  "boundary": {{
    "width_mm": 整数,
    "depth_mm": 整数,
    "doors": [
      {{
        "x": 中心点X坐标(毫米),
        "y": 中心点Y坐标(毫米),
        "width": 门宽(毫米),
        "height": 门高(毫米),
        "opens_to": "内开/外开/推拉"
      }}
    ],
    "windows": [
      {{
        "x": 中心点X坐标(毫米),
        "y": 窗台Y坐标(毫米),
        "width": 窗宽(毫米),
        "height": 窗高(毫米)
      }}
    ]
  }},
  "furniture": [
    {{
      "id": "唯一标识符",
      "name": "家具名称（中文）",
      "center": {{
        "x_mm": 几何中心X坐标(毫米),
        "y_mm": 几何中心Y坐标(毫米),
        "rotation_degrees": 0.0
      }},
      "size": {{
        "width_mm": 宽度(毫米),
        "depth_mm": 深度(毫米),
        "height_mm": 高度(毫米)
      }},
      "material": "主要材质",
      "is_obstacle": false
    }}
  ],
  "adjacencies": [
    {{
      "source_id": "家具A的id",
      "target_id": "家具B的id",
      "relationship": "adjacent_to/blocks_access_to/beside_left/beside_right",
      "clearance_mm": 间距(毫米)
    }}
  ],
  "scale_calibration": {{
    "reference_object": "参照物名称",
    "reference_size_mm": 参照物实际尺寸(毫米),
    "pixel_to_mm_ratio": 像素到毫米的换算比
  }}
}}
</result>

【校准要求】
如果没有显式校准数据，使用以下常见参照物估算比例尺：
- 标准门宽：900mm
- 成年人身高：1700mm
- 标准瓷砖：300mm × 300mm
- A4纸短边：210mm
"""


# ════════════════════════════════════════════════════════════════════════════════
# Coordinate Conversion Utilities
# ════════════════════════════════════════════════════════════════════════════════

def meters_to_millimeters(meters: float) -> float:
    """将米转换为毫米。"""
    return meters * 1000.0


def millimeters_to_meters(mm: float) -> float:
    """将毫米转换为米。"""
    return mm / 1000.0


def anchor_to_center(
    anchor_x: float,
    anchor_y: float,
    width: float,
    depth: float,
    rotation_degrees: float = 0.0,
) -> BlueprintPosition:
    """将左下角锚点坐标转换为几何中心点坐标。

    Args:
        anchor_x: 锚点（左下角）的 X 坐标 (mm)
        anchor_y: 锚点（左下角）的 Y 坐标 (mm)
        width: 物体宽度 (mm)
        depth: 物体深度 (mm)
        rotation_degrees: 旋转角度（度）

    Returns:
        几何中心点坐标
    """
    center_x = anchor_x + width / 2.0
    center_y = anchor_y + depth / 2.0
    return BlueprintPosition(
        x_mm=round(center_x, 1),
        y_mm=round(center_y, 1),
        rotation_degrees=rotation_degrees,
    )


def center_to_anchor(
    center_x: float,
    center_y: float,
    width: float,
    depth: float,
    rotation_degrees: float = 0.0,
) -> tuple[float, float]:
    """将几何中心点坐标转换回左下角锚点坐标。

    Args:
        center_x: 几何中心的 X 坐标 (mm)
        center_y: 几何中心的 Y 坐标 (mm)
        width: 物体宽度 (mm)
        depth: 物体深度 (mm)
        rotation_degrees: 旋转角度（度）

    Returns:
        (anchor_x, anchor_y) 左下角锚点坐标
    """
    anchor_x = center_x - width / 2.0
    anchor_y = center_y - depth / 2.0
    return (anchor_x, anchor_y)


def calculate_distance_mm(x1: float, y1: float, x2: float, y2: float) -> float:
    """计算两点之间的欧几里得距离（毫米）。"""
    return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5


def calculate_clearance_mm(
    center1_x: float, center1_y: float, width1: float, depth1: float,
    center2_x: float, center2_y: float, width2: float, depth2: float,
) -> float:
    """计算两个矩形物体之间的最小间距（毫米）。

    假设物体未旋转，计算投影方向上的间距。
    """
    half_w1, half_d1 = width1 / 2.0, depth1 / 2.0
    half_w2, half_d2 = width2 / 2.0, depth2 / 2.0

    dx = abs(center2_x - center1_x) - half_w1 - half_w2
    dy = abs(center2_y - center1_y) - half_d1 - half_d2

    if dx <= 0 or dy <= 0:
        return 0.0

    return min(dx, dy)


# ════════════════════════════════════════════════════════════════════════════════
# JSON Extraction Utilities
# ════════════════════════════════════════════════════════════════════════════════

def extract_json_from_response(raw_text: str) -> dict[str, Any]:
    """从模型输出中提取 JSON，支持多种格式容错。"""
    if not raw_text or not raw_text.strip():
        raise ValueError("模型返回了空文本。")

    stripped = raw_text.strip()

    # 策略 1: XML 标签 <result>...</result>
    xml_match = re.search(
        r'<result[^>]*>(.*?)</result>',
        stripped,
        re.DOTALL | re.IGNORECASE,
    )
    if xml_match:
        candidate = xml_match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 策略 2: 第一个 { 到最后一个 }
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = stripped[first_brace:last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从响应中提取 JSON: {raw_text[:200]!r}")


def _coerce_float(value: Any, default: float) -> float:
    """将任意值强制转换为浮点数。"""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().lower().replace("mm", "").replace("毫米", "")
        try:
            return float(cleaned)
        except ValueError:
            return default
    if isinstance(value, dict):
        for key in ("value", "amount", "mm", "millimeters"):
            if key in value:
                return _coerce_float(value[key], default)
    return default


def _generate_furniture_id(name: str, index: int) -> str:
    """生成简洁的家具 ID。"""
    name_map = {
        "沙发": "sofa",
        "茶几": "table",
        "餐桌": "dining_table",
        "椅子": "chair",
        "床": "bed",
        "书桌": "desk",
        "柜子": "cabinet",
        "电视": "tv",
        "冰箱": "fridge",
        "洗衣机": "washer",
        "马桶": "toilet",
        "洗手台": "sink",
        "浴缸": "bathtub",
        "淋浴": "shower",
    }
    prefix = name_map.get(name, "item")
    return f"{prefix}_{index}"


# ════════════════════════════════════════════════════════════════════════════════
# Core API
# ════════════════════════════════════════════════════════════════════════════════

def _create_client() -> ZhipuAI:
    """创建智谱 AI 客户端。"""
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key:
        raise EnvironmentError("ZHIPUAI_API_KEY 未设置。")
    return ZhipuAI(api_key=api_key)


def _load_image_base64(image_path: str) -> str:
    """加载图片并返回 base64 编码字符串。"""
    path = Path(image_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"图片文件不存在: {path}")
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _build_calibration_instruction(ref_object: str | None, ref_size_mm: float | None) -> str:
    """构建校准指令。"""
    if ref_object and ref_size_mm:
        return f"★ 比例尺约束：已知参照物「{ref_object}」的实际尺寸为 {ref_size_mm:.0f}mm，以此为标准推算所有尺寸。"
    return ""


def _normalize_blueprint_payload(payload: dict[str, Any]) -> RoomBlueprint:
    """将模型返回的 JSON 规范化为 RoomBlueprint schema。"""
    boundary_data = payload.get("boundary", {})
    furniture_data = payload.get("furniture", [])
    adjacencies_data = payload.get("adjacencies", [])
    scale_data = payload.get("scale_calibration", {})

    # 解析边界
    boundary = BlueprintBoundary(
        width_mm=_coerce_float(boundary_data.get("width_mm"), 0),
        depth_mm=_coerce_float(boundary_data.get("depth_mm"), 0),
        walls=[],
        doors=[
            {
                "x": _coerce_float(d.get("x"), 0),
                "y": _coerce_float(d.get("y"), 0),
                "width": _coerce_float(d.get("width"), 0),
                "height": _coerce_float(d.get("height"), 0),
                "opens_to": d.get("opens_to", "未知"),
            }
            for d in boundary_data.get("doors", [])
            if isinstance(d, dict)
        ],
        windows=[
            {
                "x": _coerce_float(w.get("x"), 0),
                "y": _coerce_float(w.get("y"), 0),
                "width": _coerce_float(w.get("width"), 0),
                "height": _coerce_float(w.get("height"), 0),
            }
            for w in boundary_data.get("windows", [])
            if isinstance(w, dict)
        ],
    )

    # 解析家具
    furniture_list: list[BlueprintFurniture] = []
    for idx, item in enumerate(furniture_data if isinstance(furniture_data, list) else []):
        if not isinstance(item, dict):
            continue

        center_data = item.get("center", {})
        size_data = item.get("size", {})

        name = item.get("name", "未知物品")
        furniture_id = item.get("id") or _generate_furniture_id(name, idx + 1)

        furniture_list.append(
            BlueprintFurniture(
                id=furniture_id,
                name=name,
                center=BlueprintPosition(
                    x_mm=_coerce_float(center_data.get("x_mm", center_data.get("x", 0)), 0),
                    y_mm=_coerce_float(center_data.get("y_mm", center_data.get("y", 0)), 0),
                    rotation_degrees=_coerce_float(center_data.get("rotation_degrees", 0), 0),
                ),
                size=BlueprintDimensions(
                    width_mm=_coerce_float(size_data.get("width_mm", size_data.get("width", 100)), 100),
                    depth_mm=_coerce_float(size_data.get("depth_mm", size_data.get("depth", 100)), 100),
                    height_mm=_coerce_float(size_data.get("height_mm", size_data.get("height", 100)), 100),
                ),
                material=item.get("material", "未知材质"),
                is_obstacle=bool(item.get("is_obstacle", False)),
            )
        )

    # 解析邻接关系
    adjacencies_list: list[BlueprintAdjacency] = []
    for adj in adjacencies_data if isinstance(adjacencies_data, list) else []:
        if not isinstance(adj, dict):
            continue
        adjacencies_list.append(
            BlueprintAdjacency(
                source_id=adj.get("source_id", ""),
                target_id=adj.get("target_id", ""),
                relationship=adj.get("relationship", "adjacent_to"),
                clearance_mm=_coerce_float(adj.get("clearance_mm", 0), 0),
            )
        )

    return RoomBlueprint(
        boundary=boundary,
        furniture=furniture_list,
        adjacencies=adjacencies_list,
        scale_calibration={
            "reference_object": scale_data.get("reference_object", "估算"),
            "reference_size_mm": _coerce_float(scale_data.get("reference_size_mm"), 0),
            "pixel_to_mm_ratio": _coerce_float(scale_data.get("pixel_to_mm_ratio"), 0),
        },
    )


def analyze_room_blueprint(
    image_path: str,
    calibration_data: dict | None = None,
) -> RoomBlueprint:
    """分析单张房间照片，生成 2D 归一化中心点坐标系蓝图。

    Args:
        image_path: 图片文件路径
        calibration_data: 校准数据，格式为：
            {
                "ref_object": "门/A4纸/卷尺/...",
                "ref_size_mm": 900.0  # 参照物实际尺寸（毫米）
            }

    Returns:
        RoomBlueprint 对象，包含几何中心点坐标

    Raises:
        FileNotFoundError: 图片文件不存在
        ValueError: 图片非房间场景
        RuntimeError: 解析失败
    """
    cal = dict(calibration_data) if calibration_data else {}
    ref_object = cal.get("ref_object") or None
    ref_size_mm = float(cal["ref_size_mm"]) if cal.get("ref_size_mm") is not None else None
    calibration_instruction = _build_calibration_instruction(ref_object, ref_size_mm)

    prompt = BLUPRINT_ANALYSIS_PROMPT
    if calibration_instruction:
        prompt = prompt.replace(
            "【校准要求】",
            f"【校准要求】\n{calibration_instruction}\n",
        )

    client = _create_client()
    image_b64 = _load_image_base64(image_path)
    data_uri = f"data:image/jpeg;base64,{image_b64}"

    response = client.chat.completions.create(
        model=MODEL_VISION,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
    )

    raw_msg = response.choices[0].message
    if isinstance(raw_msg.content, list):
        content = "".join(
            part.get("text", "") for part in raw_msg.content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    else:
        content = raw_msg.content or ""

    if not content:
        raise RuntimeError("GLM-4.6V 返回了空内容。")

    try:
        payload = extract_json_from_response(content)
        return _normalize_blueprint_payload(payload)
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(f"无法解析蓝图 JSON: {exc}") from exc


def convert_room_scene_to_blueprint(room_scene: dict) -> RoomBlueprint:
    """将现有的 RoomScene 字典转换为 RoomBlueprint。

    内部坐标转换：左下角锚点 → 几何中心点，米 → 毫米

    Args:
        room_scene: 现有 RoomScene 格式的字典

    Returns:
        RoomBlueprint 对象
    """
    furniture_data = room_scene.get("furniture", [])
    blueprint_furniture: list[BlueprintFurniture] = []

    for idx, item in enumerate(furniture_data):
        dims = item.get("dimensions", {})
        pos = item.get("position", {})

        width_m = dims.get("width", 0.1)
        depth_m = dims.get("depth", 0.1)
        height_m = dims.get("height", 0.1)
        anchor_x = pos.get("x", 0.0)
        anchor_y = pos.get("y", 0.0)

        center = anchor_to_center(
            anchor_x * 1000,  # 转换为 mm
            anchor_y * 1000,
            width_m * 1000,
            depth_m * 1000,
            pos.get("rotation_degrees", 0),
        )

        blueprint_furniture.append(
            BlueprintFurniture(
                id=_generate_furniture_id(item.get("name", "item"), idx + 1),
                name=item.get("name", "未知物品"),
                center=center,
                size=BlueprintDimensions(
                    width_mm=width_m * 1000,
                    depth_mm=depth_m * 1000,
                    height_mm=height_m * 1000,
                ),
                material=item.get("material", "未知材质"),
                is_obstacle=False,
            )
        )

    boundary_data = room_scene.get("boundary", {})
    return RoomBlueprint(
        boundary=BlueprintBoundary(
            width_mm=5000,  # 默认房间大小
            depth_mm=5000,
            walls=[],
            doors=[],
            windows=[],
        ),
        furniture=blueprint_furniture,
        adjacencies=[],
        scale_calibration={
            "reference_object": "converted_from_room_scene",
            "reference_size_mm": 0,
            "pixel_to_mm_ratio": 0,
        },
    )
