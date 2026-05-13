"""Core data models for architectural room-scene compliance workflows.

This module defines two parallel model systems:
1. Pydantic BaseModels: for API serialization, validation, and external interfaces
2. TypedDict (GraphState): for LangGraph in-memory state management

【架构核心约束】
- 禁止落盘缓存: 所有上下文通过 TypedDict StateGraph 内存流转
- 坐标系锁定: 所有空间定位基于【几何中心点】(x,y)，单位强制毫米 (mm)
- 二次剪裁 (Pass 2): Agent 1 提取 BBox → 后端 Crop 图像 → Agent 2 局部分析
"""

from __future__ import annotations

import uuid
from typing import (
    Any,
    Dict,
    Literal,
    NotRequired,
    TypedDict,
)

from pydantic import BaseModel, Field


# ════════════════════════════════════════════════════════════════════════════════
# LANGGRAPH TYPEDDICT STATE SYSTEM — 内存级状态流转
# ════════════════════════════════════════════════════════════════════════════════


class FurnitureNode(TypedDict):
    """单个家具节点 — 基于几何中心点坐标系，单位毫米。

    属性说明:
    - center: [x_mm, y_mm] 几何中心点坐标，原点(0,0)为房间左下角
    - elevation_mm: 离地高度（毫米），用于插座/桌面等非落地物体
    - size: [width_mm, depth_mm, height_mm] 物体尺寸
    - bbox: [left, top, right, bottom] 像素级边界框，用于图像裁剪
    - rotation: 顺时针旋转角度（度）
    - friction_level: 表面摩擦程度预估 (high/medium/low)
    - pass_2_audit: Agent 2 填写的合规审查结果
    """
    id: str
    label: str  # 中文家具名称，如"沙发"、"茶几"
    center: tuple[float, float]  # [x_mm, y_mm] 几何中心点
    elevation_mm: float  # 离地高度（毫米），地板物体填 0
    size: tuple[float, float, float]  # [width_mm, depth_mm, height_mm]
    rotation: float  # 旋转角度（度）
    bbox: tuple[int, int, int, int]  # [left_px, top_px, right_px, bottom_px]
    material: str  # 主要材质
    friction_level: Literal["high", "medium", "low"]  # 表面摩擦程度
    is_obstacle: bool  # 是否阻断主要通道 (Agent 2 判断)
    pass_2_audit: str  # Agent 2 填写: 合规审查结果


class RoomBoundaryInfo(TypedDict):
    """房间边界信息 — 单位毫米。"""
    width_mm: float
    depth_mm: float
    walls: list[dict[str, Any]]  # [{'x': mm, 'y': mm, 'length': mm}, ...]
    doors: list[dict[str, Any]]  # [{'x': mm, 'y': mm, 'width': mm, 'height': mm, 'opens_to': str}, ...]
    windows: list[dict[str, Any]]  # [{'x': mm, 'y': mm, 'width': mm, 'height': mm}, ...]


class TopologyEdge(TypedDict):
    """拓扑边 — 两物件间的边缘净距计算结果。"""
    source_id: str
    target_id: str
    clearance_mm: float  # 最小边缘净距
    relationship: Literal["adjacent_to", "blocks_access_to", "under", "beside_left", "beside_right", "near"]


class GraphState(TypedDict):
    """LangGraph 全局记忆体 — 全程内存流转，禁止落盘。

    数据流:
    1. 输入图像 → Agent 1 (BBox 提取) → furniture_list
    2. 图像 Crop → Agent 2 (局部合规分析) → pass_2_audit
    3. 拓扑计算 → topology_matrix
    4. Agent 3 (报告生成) → final_report
    """
    # === 元数据 ===
    session_id: str  # 会话唯一标识
    room_type: str  # 房间类型: "卧室" / "客厅" / "卫生间" / "厨房"
    image_paths: list[str]  # 原始图像路径列表
    scale_calibration: dict[str, Any]  # 比例尺校准信息

    # === Pass 1: Agent 1 提取 ===
    furniture_list: list[FurnitureNode]  # 从图像提取的所有家具节点
    boundary: RoomBoundaryInfo  # 房间边界信息
    raw_vision_response: str  # Agent 1 的原始响应（用于调试）

    # === Pass 2: Agent 2 分析 ===
    crop_image_base64: NotRequired[list[str]]  # 裁剪后的局部图像（Base64）
    crop_metadata: NotRequired[list[dict[str, Any]]]  # 裁剪元数据: [{'furniture_id': str, 'size': [...]}, ...]

    # === 拓扑计算 ===
    topology_matrix: dict[str, dict[str, TopologyEdge]]  # 物件间边缘净距矩阵

    # === Pass 3: Agent 3 生成 ===
    final_report: str  # 最终合规报告
    risk_level: Literal["high", "medium", "low", "unknown"]  # 综合风险等级


# ════════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS — API 序列化 & 外部接口
# ════════════════════════════════════════════════════════════════════════════════


class Dimensions(BaseModel):
    """Physical size of an object, expressed in meters (legacy format)."""
    width: float = Field(..., gt=0, description="Object width (x-axis) in meters.")
    depth: float = Field(..., gt=0, description="Object depth (y-axis) in meters.")
    height: float = Field(..., gt=0, description="Object height (z-axis) in meters.")


class Position(BaseModel):
    """Placement of an object within a room coordinate system (legacy format).

    Coordinates represent the object anchor point in plan view and elevation.
    """
    x: float = Field(..., description="X coordinate in meters from room origin.")
    y: float = Field(..., description="Y coordinate in meters from room origin.")
    z: float = Field(0.0, description="Z elevation in meters from finished floor.")
    rotation_degrees: float = Field(0.0, description="Clockwise rotation in degrees.")


class FurnitureObject(BaseModel):
    """A furniture element placed in the room scene (legacy format)."""
    name: str = Field(..., description="Human-readable furniture name or type.")
    dimensions: Dimensions = Field(..., description="Physical dimensions of the object.")
    material: str = Field(..., description="Primary material specification.")
    position: Position = Field(..., description="Spatial placement in the room.")


class RoomBoundary(BaseModel):
    """Envelope and opening definitions for the room."""
    walls: List[str] = Field(default_factory=list, description="Wall identifiers.")
    windows: List[str] = Field(default_factory=list, description="Window identifiers.")
    doors: List[str] = Field(default_factory=list, description="Door identifiers.")


class RoomScene(BaseModel):
    """Complete architectural scene state for a single room (legacy format)."""
    furniture: List[FurnitureObject] = Field(default_factory=list)
    boundary: RoomBoundary = Field(...)


class SafetyConstraint(BaseModel):
    """A codified safety or compliance requirement."""
    rule_id: str = Field(..., description="Unique ID for the rule.")
    material_requirement: str = Field(..., description="Required material condition.")
    minimum_clearance: float = Field(..., ge=0, description="Minimum clearance in meters.")
    source_document: str = Field(..., description="Reference source.")


class ModificationProposal(BaseModel):
    """Proposed change to an existing object."""
    original_object_id: str = Field(..., description="Object being modified.")
    action: Literal["move", "replace", "resize"] = Field(..., description="Modification type.")
    new_parameters: Dict[str, object] = Field(default_factory=dict)
    reasoning: str = Field(..., description="Explanation.")


# ════════════════════════════════════════════════════════════════════════════════
# BLUEPRINT MODELS — 新架构坐标系（几何中心点，单位毫米）
# ════════════════════════════════════════════════════════════════════════════════


class BlueprintDimensions(BaseModel):
    """Physical dimensions in millimeters."""
    width_mm: float = Field(..., gt=0)
    depth_mm: float = Field(..., gt=0)
    height_mm: float = Field(..., gt=0)


class BlueprintPosition(BaseModel):
    """2D geometric center position in millimeters.

    Coordinate system: origin (0,0) at bottom-left, X→right, Y→up.
    """
    x_mm: float = Field(..., ge=0)
    y_mm: float = Field(..., ge=0)
    rotation_degrees: float = Field(0.0)


class BlueprintFurniture(BaseModel):
    """A furniture element with center-point positioning."""
    id: str = Field(...)
    name: str = Field(...)
    center: BlueprintPosition = Field(...)
    size: BlueprintDimensions = Field(...)
    material: str = Field(default="未知材质")
    is_obstacle: bool = Field(default=False)
    bbox_px: tuple[int, int, int, int] | None = Field(default=None)  # [l,t,r,b]


class BlueprintBoundary(BaseModel):
    """Room boundary with millimeter precision."""
    width_mm: float = Field(..., gt=0)
    depth_mm: float = Field(..., gt=0)
    walls: List[Dict[str, float]] = Field(default_factory=list)
    doors: List[Dict[str, Any]] = Field(default_factory=list)
    windows: List[Dict[str, Any]] = Field(default_factory=list)


class BlueprintAdjacency(BaseModel):
    """Adjacency relationship between furniture items."""
    source_id: str = Field(...)
    target_id: str = Field(...)
    relationship: str = Field(...)
    clearance_mm: float = Field(0.0)


class RoomBlueprint(BaseModel):
    """Complete 2D floor plan with normalized center-point coordinates in mm."""
    boundary: BlueprintBoundary = Field(...)
    furniture: List[BlueprintFurniture] = Field(default_factory=list)
    adjacencies: List[BlueprintAdjacency] = Field(default_factory=list)
    scale_calibration: Dict[str, Any] = Field(default_factory=dict)


# ════════════════════════════════════════════════════════════════════════════════
# CONVERSION UTILITIES
# ════════════════════════════════════════════════════════════════════════════════

def furniture_node_to_blueprint(node: FurnitureNode) -> BlueprintFurniture:
    """将 FurnitureNode 转换为 BlueprintFurniture (Pydantic 格式)。"""
    x, y = node["center"]
    w, d, h = node["size"]
    return BlueprintFurniture(
        id=node["id"],
        name=node["label"],
        center=BlueprintPosition(x_mm=x, y_mm=y, rotation_degrees=node["rotation"]),
        size=BlueprintDimensions(width_mm=w, depth_mm=d, height_mm=h),
        material=node["material"],
        is_obstacle=node["is_obstacle"],
        bbox_px=node["bbox"],
    )


def generate_furniture_id(label: str, index: int) -> str:
    """生成简洁的家具 ID (英文前缀 + 数字)。"""
    name_map: dict[str, str] = {
        "沙发": "sofa", "茶几": "table", "餐桌": "dining_table",
        "椅子": "chair", "床": "bed", "书桌": "desk",
        "柜子": "cabinet", "电视": "tv", "冰箱": "fridge",
        "洗衣机": "washer", "马桶": "toilet", "洗手台": "sink",
        "浴缸": "bathtub", "淋浴": "shower", "地毯": "rug",
        "窗帘": "curtain", "书架": "shelf", "床头柜": "nightstand",
    }
    prefix = name_map.get(label, "item")
    return f"{prefix}_{index}"


def create_initial_state(
    session_id: str | None = None,
    room_type: str = "客厅",
    image_paths: list[str] | None = None,
) -> GraphState:
    """创建初始 GraphState。"""
    return GraphState(
        session_id=session_id or str(uuid.uuid4())[:8],
        room_type=room_type,
        image_paths=image_paths or [],
        scale_calibration={},
        furniture_list=[],
        boundary=RoomBoundaryInfo(
            width_mm=0,
            depth_mm=0,
            walls=[],
            doors=[],
            windows=[],
        ),
        raw_vision_response="",
        topology_matrix={},
        final_report="",
        risk_level="unknown",
    )
