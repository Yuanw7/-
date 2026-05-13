"""Image Processor — 二次剪裁 (Pass 2) 与坐标系锁定模块。

【架构核心约束】
1. 禁止落盘缓存: 所有图像数据通过 Base64 内存流转
2. 二次剪裁 (Pass 2): Agent 1 提取 BBox → 后端 Crop → 局部切片图
3. 坐标系锁定: 几何中心点 (x,y)，单位毫米

【功能】
- 根据 BBox 坐标裁剪图像局部区域
- 生成裁剪图 Base64 + 对应物件尺寸数据
- 并发准备：为 Agent 2 提供独立裁剪图批次
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Any

# PIL/Pillow for image cropping
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# ════════════════════════════════════════════════════════════════════════════════
# Data Structures
# ════════════════════════════════════════════════════════════════════════════════


@dataclass
class CropRegion:
    """裁剪区域定义。

    属性:
    - furniture_id: 对应家具的唯一标识
    - pixel_bbox: [left_px, top_px, right_px, bottom_px] 像素边界框
    - center_mm: (x_mm, y_mm) 几何中心点坐标（毫米）
    - size_mm: (width_mm, depth_mm, height_mm) 尺寸（毫米）
    - margin_px: 裁剪时额外增加的边距（像素），用于保留上下文
    """
    furniture_id: str
    pixel_bbox: tuple[int, int, int, int]  # [left, top, right, bottom]
    center_mm: tuple[float, float]  # (x_mm, y_mm)
    size_mm: tuple[float, float, float]  # (width, depth, height)
    margin_px: int = 20  # 默认边距 20px


@dataclass
class CropResult:
    """单个裁剪结果。"""
    furniture_id: str
    image_base64: str  # 裁剪图 Base64
    center_mm: tuple[float, float]
    size_mm: tuple[float, float, float]
    original_bbox: tuple[int, int, int, int]  # 原始边界框
    crop_bbox: tuple[int, int, int, int]  # 实际裁剪边界框（含边距）


@dataclass
class CropBatchResult:
    """批量裁剪结果（供 Agent 2 并发分析）。"""
    crops: list[CropResult]
    room_width_px: int
    room_height_px: int
    pixel_to_mm_ratio: float  # 像素到毫米的换算比


# ════════════════════════════════════════════════════════════════════════════════
# Core Cropping Functions
# ════════════════════════════════════════════════════════════════════════════════


def crop_image_by_bbox(
    image_source: Image.Image | str | bytes,
    crop_region: CropRegion,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """根据 BBox 裁剪图像。

    Args:
        image_source: PIL Image 对象，或图像路径，或 bytes
        crop_region: 裁剪区域定义

    Returns:
        (裁剪后的 PIL Image, 实际裁剪边界框 [l,t,r,b])

    Raises:
        ImportError: PIL 不可用
        ValueError: 图像加载失败
    """
    if not PIL_AVAILABLE:
        raise ImportError("PIL (Pillow) 未安装，请运行: pip install Pillow")

    # 加载图像
    if isinstance(image_source, Image.Image):
        img = image_source
    elif isinstance(image_source, str):
        img = Image.open(image_source)
    elif isinstance(image_source, bytes):
        img = Image.open(io.BytesIO(image_source))
    else:
        raise ValueError(f"不支持的图像源类型: {type(image_source)}")

    # 转换为 RGB（确保兼容 JPEG）
    if img.mode != "RGB":
        img = img.convert("RGB")

    # 计算实际裁剪边界（含边距）
    left, top, right, bottom = crop_region.pixel_bbox
    margin = crop_region.margin_px

    # 确保不超出图像边界
    img_width, img_height = img.size
    actual_left = max(0, left - margin)
    actual_top = max(0, top - margin)
    actual_right = min(img_width, right + margin)
    actual_bottom = min(img_height, bottom + margin)

    # 裁剪
    cropped = img.crop((actual_left, actual_top, actual_right, actual_bottom))

    actual_bbox = (actual_left, actual_top, actual_right, actual_bottom)
    return cropped, actual_bbox


def crop_to_base64(
    image_source: Image.Image | str | bytes,
    crop_region: CropRegion,
    format: str = "JPEG",
    quality: int = 85,
) -> str:
    """裁剪图像并返回 Base64 编码。

    Args:
        image_source: 图像源
        crop_region: 裁剪区域
        format: 输出格式（JPEG/PNG）
        quality: JPEG 质量 (1-100)

    Returns:
        Base64 编码字符串（不含 data URI 前缀）
    """
    cropped, _ = crop_image_by_bbox(image_source, crop_region)

    buffer = io.BytesIO()
    cropped.save(buffer, format=format, quality=quality)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def crop_batch(
    image_source: Image.Image | str | bytes,
    crop_regions: list[CropRegion],
) -> CropBatchResult:
    """批量裁剪 — 为 Agent 2 并发分析准备数据。

    Args:
        image_source: 原始图像
        crop_regions: 裁剪区域列表

    Returns:
        CropBatchResult: 包含所有裁剪结果
    """
    if not PIL_AVAILABLE:
        raise ImportError("PIL (Pillow) 未安装")

    # 加载图像获取尺寸
    if isinstance(image_source, Image.Image):
        img = image_source
    elif isinstance(image_source, str):
        img = Image.open(image_source)
    elif isinstance(image_source, bytes):
        img = Image.open(io.BytesIO(image_source))
    else:
        raise ValueError(f"不支持的图像源类型: {type(image_source)}")

    room_width_px, room_height_px = img.size

    # 计算像素到毫米的换算比（基于第一个裁剪区域的已知尺寸估算）
    # TODO (后续细节调整): 应从 state['scale_calibration'] 获取精确比例尺
    pixel_to_mm_ratio = 0.5  # 默认估算：每像素约 0.5mm

    crops: list[CropResult] = []

    for region in crop_regions:
        cropped_img, actual_bbox = crop_image_by_bbox(image_source, region)

        # 转换为 Base64
        buffer = io.BytesIO()
        cropped_img.save(buffer, format="JPEG", quality=85)
        image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        crops.append(CropResult(
            furniture_id=region.furniture_id,
            image_base64=image_b64,
            center_mm=region.center_mm,
            size_mm=region.size_mm,
            original_bbox=region.pixel_bbox,
            crop_bbox=actual_bbox,
        ))

    return CropBatchResult(
        crops=crops,
        room_width_px=room_width_px,
        room_height_px=room_height_px,
        pixel_to_mm_ratio=pixel_to_mm_ratio,
    )


# ════════════════════════════════════════════════════════════════════════════════
# Coordinate Utilities
# ════════════════════════════════════════════════════════════════════════════════

def estimate_pixel_to_mm_ratio(
    known_width_mm: float,
    pixel_bbox: tuple[int, int, int, int],
) -> float:
    """根据已知尺寸估算像素到毫米的换算比。

    Args:
        known_width_mm: 已知宽度（毫米）
        pixel_bbox: 像素边界框 [left, top, right, bottom]

    Returns:
        像素到毫米的换算比 (mm/px)
    """
    left, _, right, _ = pixel_bbox
    pixel_width = right - left
    if pixel_width <= 0:
        return 1.0  # 默认值
    return known_width_mm / pixel_width


def bbox_to_center_size_mm(
    pixel_bbox: tuple[int, int, int, int],
    pixel_to_mm_ratio: float,
) -> tuple[tuple[float, float], tuple[float, float, float]]:
    """将像素 BBox 转换为几何中心点坐标和尺寸（毫米）。

    Args:
        pixel_bbox: [left_px, top_px, right_px, bottom_px]
        pixel_to_mm_ratio: 像素到毫米换算比

    Returns:
        (center_mm, size_mm) = ((x, y), (width, depth, height))
    """
    left, top, right, bottom = pixel_bbox
    pixel_width = right - left
    pixel_height = bottom - top

    center_x_px = (left + right) / 2
    center_y_px = (top + bottom) / 2

    # 假设 height = depth（简化）
    center_mm = (center_x_px * pixel_to_mm_ratio, center_y_px * pixel_to_mm_ratio)
    size_mm = (
        pixel_width * pixel_to_mm_ratio,
        pixel_height * pixel_to_mm_ratio,
        pixel_height * pixel_to_mm_ratio,
    )

    return center_mm, size_mm


# ════════════════════════════════════════════════════════════════════════════════
# Integration with GraphState
# ════════════════════════════════════════════════════════════════════════════════

def process_crops_for_agent2(
    image_path: str,
    furniture_list: list[dict[str, Any]],
) -> dict[str, Any]:
    """从 GraphState 的 furniture_list 生成 Agent 2 所需的裁剪数据。

    【注意】此函数为框架定义，待与 vision_engine.py 集成。

    Args:
        image_path: 原始图像路径
        furniture_list: GraphState['furniture_list']

    Returns:
        {
            'crop_image_base64': [base64_str, ...],
            'crop_metadata': [{'furniture_id': str, 'center_mm': [], 'size_mm': []}, ...]
        }
    """
    # TODO (后续细节调整):
    # 1. 根据 furniture_list 中的 bbox 构建 CropRegion 列表
    # 2. 调用 crop_batch 生成裁剪图
    # 3. 返回 Agent 2 所需的格式

    crop_image_base64: list[str] = []
    crop_metadata: list[dict[str, Any]] = []

    # placeholder
    return {
        "crop_image_base64": crop_image_base64,
        "crop_metadata": crop_metadata,
    }


# ════════════════════════════════════════════════════════════════════════════════
# Placeholder Functions (待后续实现)
# ════════════════════════════════════════════════════════════════════════════════

def preprocess_image(image_path: str) -> Image.Image | None:
    """图像预处理（待后续细节调整）。

    - 调整方向（EXIF）
    - 亮度/对比度均衡
    - 缩放（如果图像过大）
    """
    # TODO (后续细节调整): 实现图像预处理
    if not PIL_AVAILABLE:
        return None
    try:
        img = Image.open(image_path)
        return img.convert("RGB")
    except Exception:
        return None


def stitch_crops(crops: list[CropResult]) -> Image.Image | None:
    """将多个裁剪区域拼接回完整图像（调试用）。

    【注意】此为占位函数，待后续细节调整。
    """
    # TODO (后续细节调整): 将 Agent 2 分析后的裁剪图拼接回原图
    # 用于可视化调试
    return None
