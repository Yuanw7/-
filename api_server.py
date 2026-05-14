"""FastAPI Backend Server — 2D 房屋平面图交互 API。

核心功能：
1. AI 生成家具布局初始状态
2. WebSocket 实时审计反馈
3. REST API 审计端点

工具组合：Fabric.js (前端) + FastAPI (后端) + LangGraph (逻辑流)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from shapely.geometry import Polygon, box
from shapely.ops import transform
import shapely

from renderer import state_to_render_json, calculate_bbox_from_center, get_material_color
from models import GraphState
from agents import create_compliance_graph, run_compliance_analysis


# ════════════════════════════════════════════════════════════════════════════════
# FastAPI 应用初始化
# ════════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="适老化改造合规审查 API",
    description="2D 房屋平面图 + AI 审计 + 实时交互",
    version="1.0.0",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_server")


# ════════════════════════════════════════════════════════════════════════════════
# Pydantic 请求/响应模型
# ════════════════════════════════════════════════════════════════════════════════

class FurnitureItem(BaseModel):
    """家具项"""
    id: str
    center: list[float] = Field(..., min_length=2, max_length=2)  # [x, y] mm
    size: list[float] = Field(..., min_length=3, max_length=3)  # [w, d, h] mm
    rotation: float = 0.0  # degrees
    material: str = "未知"
    label: str = "未知"


class RoomConfig(BaseModel):
    """房间配置"""
    width: float = Field(..., gt=0)  # mm
    depth: float = Field(..., gt=0)  # mm


class CanvasState(BaseModel):
    """画布状态"""
    room: RoomConfig
    furniture: list[FurnitureItem]


class AuditRequest(BaseModel):
    """审计请求"""
    canvas_state: CanvasState
    room_type: str = "客厅"  # 客厅/卧室/卫生间/厨房


class AuditViolation(BaseModel):
    """违规项"""
    source_id: str
    target_id: str
    violation_type: str
    actual_clearance_mm: float
    required_clearance_mm: float
    shortage_mm: float
    severity: str
    suggestion: str


class AuditResponse(BaseModel):
    """审计响应"""
    violations: list[AuditViolation]
    total_violations: int
    t0_count: int
    t1_count: int
    t2_count: int
    compliance_score: float  # 0-100


class WebSocketMessage(BaseModel):
    """WebSocket 消息"""
    type: str  # "state_update" | "audit_result" | "error"
    payload: dict[str, Any]


# ════════════════════════════════════════════════════════════════════════════════
# Shapely 碰撞检测辅助
# ════════════════════════════════════════════════════════════════════════════════

def create_rectangle_polygon(center: list[float], size: list[float], rotation: float = 0.0) -> Polygon:
    """根据中心点、尺寸、旋转角度创建矩形多边形。

    Args:
        center: 中心点 [x, y] mm
        size: 尺寸 [w, d, h] mm
        rotation: 旋转角度 degrees

    Returns:
        Shapely Polygon
    """
    cx, cy = center
    w, d = size[0], size[1]

    # 原始矩形顶点 (相对于中心)
    half_w, half_d = w / 2, d / 2
    points = [
        (-half_w, -half_d),
        (half_w, -half_d),
        (half_w, half_d),
        (-half_w, half_d),
    ]

    if rotation != 0:
        import math
        rad = math.radians(rotation)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        # 旋转顶点
        rotated_points = []
        for px, py in points:
            rx = px * cos_a - py * sin_a
            ry = px * sin_a + py * cos_a
            rotated_points.append((rx + cx, ry + cy))
        points = rotated_points
    else:
        # 平移到中心
        points = [(px + cx, py + cy) for px, py in points]

    return Polygon(points)


def calculate_clearance(poly1: Polygon, poly2: Polygon) -> float:
    """计算两个多边形之间的最小边缘净距。

    Args:
        poly1: 多边形 1
        poly2: 多边形 2

    Returns:
        最小净距 (mm)，负值表示重叠
    """
    if poly1.intersects(poly2):
        # 计算重叠区域面积
        intersection = poly1.intersection(poly2)
        if intersection.area > 0:
            return -min(poly1.distance(poly2), 0)  # 返回负值表示重叠

    return poly1.distance(poly2)


def check_collision(furniture_list: list[FurnitureItem]) -> list[dict[str, Any]]:
    """检查家具之间的碰撞和净距。

    Args:
        furniture_list: 家具列表

    Returns:
        碰撞/净距检测结果列表
    """
    results = []

    for i, item_a in enumerate(furniture_list):
        poly_a = create_rectangle_polygon(item_a.center, item_a.size, item_a.rotation)

        for item_b in furniture_list[i + 1:]:
            poly_b = create_rectangle_polygon(item_b.center, item_b.size, item_b.rotation)

            # 检查是否相交
            intersects = poly_a.intersects(poly_b)

            # 计算最小距离
            if intersects:
                clearance = -poly_a.distance(poly_b)
                relationship = "overlap"
            else:
                clearance = poly_a.distance(poly_b)
                relationship = "near"

            results.append({
                "source_id": item_a.id,
                "target_id": item_b.id,
                "clearance_mm": clearance,
                "intersects": intersects,
                "relationship": relationship,
            })

    return results


# ════════════════════════════════════════════════════════════════════════════════
# 合规标准
# ════════════════════════════════════════════════════════════════════════════════

CLEARANCE_STANDARDS = {
    "wheelchair_passage": 900,  # 轮椅通道 mm
    "bed_side_clearance": 600,  # 床侧净距 mm
    "door_access_clearance": 800,  # 门侧净距 mm
}


def classify_violation(clearance_mm: float, violation_type: str = "wheelchair_passage") -> dict[str, Any]:
    """根据净距分类违规等级。

    Args:
        clearance_mm: 实测净距
        violation_type: 违规类型

    Returns:
        违规详情
    """
    required = CLEARANCE_STANDARDS.get(violation_type, 900)
    shortage = max(0, required - clearance_mm)

    if clearance_mm < 0 or shortage > required * 0.5:
        severity = "T0"  # 严重
    elif shortage > required * 0.3:
        severity = "T1"  # 中等
    else:
        severity = "T2"  # 一般

    # 整改建议
    if severity == "T0":
        suggestion = "立即整改，建议更换适老家具或重新布局"
    elif severity == "T1":
        suggestion = "7天内整改，可考虑微调家具位置"
    else:
        suggestion = "30天内优化，注意保持通道畅通"

    return {
        "actual_clearance_mm": clearance_mm,
        "required_clearance_mm": required,
        "shortage_mm": shortage,
        "severity": severity,
        "suggestion": suggestion,
    }


# ════════════════════════════════════════════════════════════════════════════════
# REST API 端点
# ════════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def root():
    """返回前端页面"""
    with open("static/floorplan.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/audit", response_model=AuditResponse)
async def audit_canvas(request: AuditRequest):
    """审计画布状态，返回违规项列表。

    Args:
        request: 审计请求

    Returns:
        审计结果
    """
    logger.info(f"审计请求: {len(request.canvas_state.furniture)} 件家具")

    # 碰撞检测
    collision_results = check_collision(request.canvas_state.furniture)

    violations = []
    t0_count = 0
    t1_count = 0
    t2_count = 0

    for result in collision_results:
        if result["clearance_mm"] < CLEARANCE_STANDARDS["wheelchair_passage"]:
            violation = classify_violation(
                result["clearance_mm"],
                "wheelchair_passage"
            )

            violations.append(AuditViolation(
                source_id=result["source_id"],
                target_id=result["target_id"],
                violation_type=result["relationship"],
                actual_clearance_mm=violation["actual_clearance_mm"],
                required_clearance_mm=violation["required_clearance_mm"],
                shortage_mm=violation["shortage_mm"],
                severity=violation["severity"],
                suggestion=violation["suggestion"],
            ))

            if violation["severity"] == "T0":
                t0_count += 1
            elif violation["severity"] == "T1":
                t1_count += 1
            else:
                t2_count += 1

    # 计算合规分数
    total_pairs = len(collision_results)
    if total_pairs > 0:
        compliant_pairs = sum(1 for r in collision_results if r["clearance_mm"] >= CLEARANCE_STANDARDS["wheelchair_passage"])
        compliance_score = (compliant_pairs / total_pairs) * 100
    else:
        compliance_score = 100.0

    return AuditResponse(
        violations=violations,
        total_violations=len(violations),
        t0_count=t0_count,
        t1_count=t1_count,
        t2_count=t2_count,
        compliance_score=round(compliance_score, 1),
    )


@app.post("/api/generate-layout")
async def generate_layout(room_type: str = "客厅", room_width: float = 6000, room_depth: float = 4500):
    """AI 生成初始家具布局。

    Args:
        room_type: 房间类型
        room_width: 房间宽度 mm
        room_depth: 房间深度 mm

    Returns:
        生成的布局 JSON
    """
    logger.info(f"生成布局: {room_type} {room_width}x{room_depth}")

    # 模拟 AI 生成的布局
    # 实际项目中这里会调用 LangGraph 进行真实分析
    furniture = []

    if room_type == "客厅":
        furniture = [
            FurnitureItem(
                id="sofa_1",
                center=[3000, 3500],
                size=[1800, 850, 900],
                rotation=0,
                material="布艺",
                label="沙发"
            ),
            FurnitureItem(
                id="coffee_table_1",
                center=[3000, 2800],
                size=[1000, 600, 450],
                rotation=0,
                material="木质",
                label="茶几"
            ),
            FurnitureItem(
                id="tv_stand_1",
                center=[3000, 500],
                size=[1500, 400, 500],
                rotation=0,
                material="人造板",
                label="电视柜"
            ),
            FurnitureItem(
                id="armchair_1",
                center=[1500, 3000],
                size=[800, 800, 850],
                rotation=0,
                material="皮革",
                label="单人椅"
            ),
        ]
    elif room_type == "卧室":
        furniture = [
            FurnitureItem(
                id="bed_1",
                center=[3000, 3000],
                size=[2000, 1800, 500],
                rotation=0,
                material="布料",
                label="床"
            ),
            FurnitureItem(
                id="nightstand_1",
                center=[1800, 3000],
                size=[500, 400, 600],
                rotation=0,
                material="木质",
                label="床头柜"
            ),
            FurnitureItem(
                id="wardrobe_1",
                center=[5500, 3000],
                size=[800, 600, 2000],
                rotation=0,
                material="人造板",
                label="衣柜"
            ),
        ]

    return {
        "room": RoomConfig(width=room_width, depth=room_depth),
        "furniture": [f.model_dump() for f in furniture],
    }


@app.get("/api/materials")
async def get_materials():
    """获取材质列表"""
    return [
        {"id": "木质", "color": "#8B4513"},
        {"id": "实木", "color": "#A0522D"},
        {"id": "人造板", "color": "#DEB887"},
        {"id": "金属", "color": "#708090"},
        {"id": "玻璃", "color": "#87CEEB"},
        {"id": "石材", "color": "#808080"},
        {"id": "布艺", "color": "#DEB887"},
        {"id": "皮革", "color": "#8B0000"},
        {"id": "塑料", "color": "#FFB6C1"},
    ]


# ════════════════════════════════════════════════════════════════════════════════
# WebSocket 端点 — 实时审计
# ════════════════════════════════════════════════════════════════════════════════

class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket 连接建立，当前连接数: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket 断开，当前连接数: {len(self.active_connections)}")

    async def send_audit_result(self, websocket: WebSocket, result: dict[str, Any]):
        await websocket.send_json({
            "type": "audit_result",
            "payload": result,
        })

    async def broadcast(self, message: dict[str, Any]):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


@app.websocket("/ws/audit")
async def websocket_audit(websocket: WebSocket):
    """WebSocket 实时审计端点。

    前端发送画布状态，后端返回实时审计结果。

    消息格式:
    - 发送: {"type": "state_update", "payload": {"room": {...}, "furniture": [...]}}
    - 接收: {"type": "audit_result", "payload": {...}}
    """
    await manager.connect(websocket)

    try:
        while True:
            # 接收前端消息
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "state_update":
                payload = data.get("payload", {})

                # 转换为 AuditRequest
                furniture_items = [
                    FurnitureItem(**f) for f in payload.get("furniture", [])
                ]
                room_data = payload.get("room", {})

                audit_request = AuditRequest(
                    canvas_state=CanvasState(
                        room=RoomConfig(**room_data),
                        furniture=furniture_items,
                    ),
                    room_type=payload.get("room_type", "客厅"),
                )

                # 执行审计
                audit_response = await audit_canvas(audit_request)

                # 发送结果
                await websocket.send_json({
                    "type": "audit_result",
                    "payload": audit_response.model_dump(),
                })

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
        manager.disconnect(websocket)


@app.websocket("/ws/sync")
async def websocket_sync(websocket: WebSocket):
    """WebSocket 同步端点 — 多人协作时同步状态。

    Args:
        websocket: WebSocket 连接
    """
    await manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_json()

            # 广播消息给所有连接的客户端
            await manager.broadcast({
                "type": "sync",
                "payload": data,
            })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket 同步错误: {e}")
        manager.disconnect(websocket)


# ════════════════════════════════════════════════════════════════════════════════
# 启动配置
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
