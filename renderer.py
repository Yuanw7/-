"""Renderer Engine — 前端渲染器。

Role: 资深建筑测绘工程师

Task: 提取家具几何元数据，生成可供交互界面（Fabric.js/Konva）直接渲染的 JSON 状态。

Chain-of-Thought (CoT):
1. 原点对齐：识别房间左下角并定义为 (0,0)
2. 中心锚定：计算每个家具的几何中心点 (x, y)
3. 包围盒计算：输出 2D 投影尺寸（宽、深）以及离地高度 (z)
4. 交互预设：为每个物件分配唯一 id

Constraint:
- 长度单位: mm
- 角度单位: degrees
- 禁止输出自然语言解释
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from models import GraphState, FurnitureNode


@dataclass
class RenderObject:
    """可渲染对象"""
    id: str
    center: list[float]  # [x, y] 单位 mm
    size: list[float]  # [width, depth, height] 单位 mm
    rotation: float  # degrees
    material: str
    label: str
    elevation_mm: float  # 离地高度


# ════════════════════════════════════════════════════════════════════════════════
# Chain-of-Thought: 原点对齐与坐标转换
# ════════════════════════════════════════════════════════════════════════════════

def align_origin(boundary_width_mm: float, boundary_depth_mm: float) -> tuple[float, float]:
    """CoT 步骤1: 原点对齐

    识别房间左下角并定义为 (0, 0)

    Args:
        boundary_width_mm: 房间宽度 (X方向)
        boundary_depth_mm: 房间深度 (Y方向)

    Returns:
        原点偏移量 (origin_x, origin_y) = (0, 0) 房间左下角
    """
    origin_x = 0.0
    origin_y = 0.0
    return origin_x, origin_y


def calculate_center_anchor(
    furniture: FurnitureNode,
    origin_x: float,
    origin_y: float,
) -> list[float]:
    """CoT 步骤2: 中心锚定

    计算家具的几何中心点 (x, y)，使用中心点以适配前端旋转逻辑

    Args:
        furniture: 家具节点
        origin_x: 原点 X 偏移
        origin_y: 原点 Y 偏移

    Returns:
        中心点坐标 [x, y] 单位 mm
    """
    cx, cy = furniture.get("center", [0, 0])

    return [
        float(cx - origin_x),
        float(cy - origin_y),
    ]


def calculate_bounding_box(furniture: FurnitureNode) -> list[float]:
    """CoT 步骤3: 包围盒计算

    输出家具的 2D 投影尺寸（宽、深）以及离地高度 (z)

    Args:
        furniture: 家具节点

    Returns:
        [width, depth, height] 单位 mm
    """
    size = furniture.get("size", [100, 100, 100])
    return [
        float(size[0]),  # width
        float(size[1]),  # depth
        float(size[2]),  # height
    ]


# ════════════════════════════════════════════════════════════════════════════════
# 主渲染函数
# ════════════════════════════════════════════════════════════════════════════════

def state_to_render_json(state: GraphState) -> dict[str, Any]:
    """将 GraphState 转换为前端渲染 JSON。

    整合 CoT 四步骤，生成可供 Fabric.js/Konva 直接渲染的 JSON 状态。

    输出格式:
    {
        "room": {"w": mm, "d": mm},
        "furniture": [
            {
                "id": str,
                "center": [x, y],
                "size": [w, d, h],
                "rotation": float,
                "material": str,
                "label": str,
                "elevation_mm": float
            }
        ]
    }

    Args:
        state: GraphState

    Returns:
        前端渲染 JSON
    """
    boundary = state.get("boundary", {})
    furniture_list = state.get("furniture_list", [])

    room_w = boundary.get("width_mm", 0)
    room_d = boundary.get("depth_mm", 0)

    origin_x, origin_y = align_origin(room_w, room_d)

    furniture_output = []

    for item in furniture_list:
        center = calculate_center_anchor(item, origin_x, origin_y)
        size = calculate_bounding_box(item)
        rotation = float(item.get("rotation", 0.0))
        material = item.get("material", "未知")
        label = item.get("label", "未知物品")
        elevation = float(item.get("elevation_mm", 0.0))

        furniture_output.append({
            "id": item.get("id", f"item_{len(furniture_output)}"),
            "center": center,
            "size": size,
            "rotation": rotation,
            "material": material,
            "label": label,
            "elevation_mm": elevation,
        })

    return {
        "room": {
            "w": room_w,
            "d": room_d,
        },
        "furniture": furniture_output,
    }


def furniture_to_render_object(furniture: FurnitureNode) -> RenderObject:
    """将单个家具节点转换为 RenderObject。

    Args:
        furniture: 家具节点

    Returns:
        RenderObject
    """
    cx, cy = furniture.get("center", [0, 0])
    size = furniture.get("size", [100, 100, 100])
    material = furniture.get("material", "未知")

    return RenderObject(
        id=furniture.get("id", "unknown"),
        center=[float(cx), float(cy)],
        size=[float(size[0]), float(size[1]), float(size[2])],
        rotation=float(furniture.get("rotation", 0.0)),
        material=material,
        label=furniture.get("label", "未知"),
        elevation_mm=float(furniture.get("elevation_mm", 0.0)),
    )


def render_objects_to_json(objects: list[RenderObject]) -> dict[str, Any]:
    """将 RenderObject 列表转换为前端渲染 JSON。

    Args:
        objects: RenderObject 列表

    Returns:
        前端渲染 JSON
    """
    return {
        "furniture": [
            {
                "id": obj.id,
                "center": obj.center,
                "size": obj.size,
                "rotation": obj.rotation,
                "material": obj.material,
                "label": obj.label,
                "elevation_mm": obj.elevation_mm,
            }
            for obj in objects
        ]
    }


# ════════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════════════════════════════════

def mm_to_pixels(mm: float, scale: float = 1.0) -> float:
    """毫米转像素

    Args:
        mm: 毫米值
        scale: 比例尺 (默认 1px = 1mm)

    Returns:
        像素值
    """
    return mm * scale


def pixels_to_mm(pixels: float, scale: float = 1.0) -> float:
    """像素转毫米

    Args:
        pixels: 像素值
        scale: 比例尺

    Returns:
        毫米值
    """
    return pixels / scale


def calculate_bbox_from_center(
    center: list[float],
    size: list[float],
    rotation: float = 0.0,
) -> dict[str, float]:
    """根据中心点和尺寸计算包围盒。

    用于 Fabric.js 的 set() 方法。

    Args:
        center: 中心点 [x, y]
        size: 尺寸 [w, d, h]
        rotation: 旋转角度 (degrees)

    Returns:
        Fabric.js bbox {
            "left": float,
            "top": float,
            "width": float,
            "height": float,
            "angle": float
        }
    """
    w, d, _ = size

    if rotation != 0:
        import math
        rad = math.radians(abs(rotation))
        cos_a = abs(math.cos(rad))
        sin_a = abs(math.sin(rad))
        rotated_w = w * cos_a + d * sin_a
        rotated_d = w * sin_a + d * cos_a
    else:
        rotated_w = w
        rotated_d = d

    return {
        "left": center[0] - rotated_w / 2,
        "top": center[1] - rotated_d / 2,
        "width": rotated_w,
        "height": rotated_d,
        "angle": rotation,
    }


def generate_fabric_config(obj: RenderObject, scale: float = 1.0) -> dict[str, Any]:
    """生成 Fabric.js 对象配置。

    Args:
        obj: RenderObject
        scale: 比例尺 (px/mm)

    Returns:
        Fabric.js 配置
    """
    bbox = calculate_bbox_from_center(obj.center, obj.size, obj.rotation)

    return {
        "type": "rect",
        "left": mm_to_pixels(bbox["left"], scale),
        "top": mm_to_pixels(bbox["top"], scale),
        "width": mm_to_pixels(bbox["width"], scale),
        "height": mm_to_pixels(bbox["height"], scale),
        "angle": obj.rotation,
        "originX": "center",
        "originY": "center",
        "fill": get_material_color(obj.material),
        "stroke": "#333333",
        "strokeWidth": 2,
        "selectable": True,
        "hasControls": True,
        "hasBorders": True,
        "data": {
            "id": obj.id,
            "material": obj.material,
            "label": obj.label,
            "elevation_mm": obj.elevation_mm,
        },
    }


def get_material_color(material: str) -> str:
    """根据材质获取默认颜色。

    Args:
        material: 材质类型

    Returns:
        HEX 颜色值
    """
    color_map = {
        "木质": "#8B4513",
        "实木": "#A0522D",
        "人造板": "#DEB887",
        "金属": "#708090",
        "不锈钢": "#C0C0C0",
        "铝合金": "#B8B8B8",
        "玻璃": "#87CEEB",
        "钢化玻璃": "#ADD8E6",
        "石材": "#808080",
        "大理石": "#D3D3D3",
        "瓷砖": "#F5F5F5",
        "陶瓷": "#FFFAF0",
        "皮革": "#8B0000",
        "布艺": "#DEB887",
        "织物": "#F5DEB3",
        "塑料": "#FFB6C1",
        "未知": "#D3D3D3",
    }

    return color_map.get(material, "#D3D3D3")
