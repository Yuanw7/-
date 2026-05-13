"""Agent 3: 无障碍设计审核引擎 — 空间冲突审查与规范碰撞检测。

Role: 严苛的国家注册无障碍设计审核员

Chain-of-Thought 执行逻辑:
1. 数据摄入：读取所有对象的中心点 (x,y)、尺寸 (width, depth) 及预设的最小安全净距
2. 距离计算：执行几何函数，计算两两物体间的实际最短边缘净距
3. 规范碰撞：调取 GB 规范，核对实际净距是否 < 规范净距
4. 动线审查：连接床-卫生间、门-床的最短路径，检查是否被家具阻挡

约束：
- 采用最严格解释原则：当多项规范冲突时，取最大安全净距或最高防火等级
- 必须引用具体 GB 条款编号
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from cn_regulation_rules import CHINESE_REGULATION_SYSTEM_RULES
from models import FurnitureNode, GraphState


# ════════════════════════════════════════════════════════════════════════════════
# 规范净距标准 (单位: mm)
# ════════════════════════════════════════════════════════════════════════════════

@dataclass
class ClearanceStandard:
    """最小安全净距规范标准"""
    name: str
    value_mm: float
    regulation_ref: str
    description: str


CLEARANCE_STANDARDS = {
    # 无障碍通道
    "wheelchair_passage": ClearanceStandard(
        name="轮椅通道净宽",
        value_mm=900,
        regulation_ref="GB 50763-2012 3.4.1",
        description="轮椅使用者在直行通道的最小通过宽度",
    ),
    "wheelchair_turning": ClearanceStandard(
        name="轮椅回转空间",
        value_mm=1500,
        regulation_ref="GB 50763-2012 3.5.3",
        description="轮椅旋转180度的最小空间直径",
    ),
    "door_access_clearance": ClearanceStandard(
        name="门侧净距",
        value_mm=800,
        regulation_ref="GB 50763-2012 3.6.2",
        description="门开启侧墙面与最近家具的最小距离",
    ),

    # 家具周边
    "bed_side_clearance": ClearanceStandard(
        name="床侧净距",
        value_mm=800,
        regulation_ref="GB 50763-2012 4.4.3",
        description="床侧方便老年人起身扶持的最小空间",
    ),
    "toilet_clearance": ClearanceStandard(
        name="马桶侧净距",
        value_mm=600,
        regulation_ref="GB 50763-2012 4.4.5",
        description="马桶侧面扶手安装及轮椅转移的最小空间",
    ),
    "grab_bar_clearance": ClearanceStandard(
        name="扶手抓握净距",
        value_mm=500,
        regulation_ref="GB 50763-2012 4.4.6",
        description="安全抓杆外侧与障碍物的最小距离",
    ),

    # 地面安全
    "threshold_height": ClearanceStandard(
        name="门槛高度",
        value_mm=20,
        regulation_ref="GB 50763-2012 3.6.1",
        description="室内地坪高差不应大于此值",
    ),
}


@dataclass
class ViolationRecord:
    """违规记录"""
    source_id: str
    target_id: str
    violation_type: str
    actual_clearance_mm: float
    required_clearance_mm: float
    shortage_mm: float  # 短缺量 = required - actual
    regulation_ref: str
    severity: str  # high/medium/low
    description: str


@dataclass
class ClearanceResult:
    """净距计算结果"""
    source_id: str
    target_id: str
    dx_mm: float  # X方向距离
    dy_mm: float  # Y方向距离
    actual_clearance_mm: float  # 实际最小净距
    standard_type: str  # 适用的净距标准类型


@dataclass
class PathAnalysis:
    """动线分析结果"""
    path_name: str  # 如 "床→卫生间"
    source_id: str
    target_id: str
    blocking_objects: list[str] = field(default_factory=list)
    shortest_path_clearance_mm: float = 0.0
    is_blocked: bool = False
    alternative_route_exists: bool = False


# ════════════════════════════════════════════════════════════════════════════════
# 几何计算函数
# ════════════════════════════════════════════════════════════════════════════════

def calculate_edge_clearance(
    node_a: FurnitureNode,
    node_b: FurnitureNode,
) -> ClearanceResult:
    """计算两个物体间的边缘净距。

    Args:
        node_a: 物体A
        node_b: 物体B

    Returns:
        ClearanceResult，包含dx、dy和最小净距
    """
    cx_a, cy_a = node_a["center"]
    cx_b, cy_b = node_b["center"]

    w_a, d_a, _ = node_a["size"]
    w_b, d_b, _ = node_b["size"]

    # 半尺寸
    half_w_a, half_d_a = w_a / 2, d_a / 2
    half_w_b, half_d_b = w_b / 2, d_b / 2

    # 中心距离
    dx = abs(cx_b - cx_a)
    dy = abs(cy_b - cy_a)

    # 边缘净距 = 中心距离 - 两个物体的半尺寸之和
    edge_dx = dx - half_w_a - half_w_b
    edge_dy = dy - half_d_a - half_d_b

    # 最小边缘净距（两物体间的最短通道宽度）
    actual_clearance = min(
        max(0, edge_dx) if edge_dx > 0 else 0,
        max(0, edge_dy) if edge_dy > 0 else 0,
    )

    return ClearanceResult(
        source_id=node_a["id"],
        target_id=node_b["id"],
        dx_mm=max(0, edge_dx),
        dy_mm=max(0, edge_dy),
        actual_clearance_mm=max(0, actual_clearance),
        standard_type="wheelchair_passage",
    )


def calculate_path_blocking(
    state: GraphState,
    source_label: str,
    target_label: str,
) -> PathAnalysis:
    """分析两点间动线是否被家具阻挡。

    Args:
        state: 图状态
        source_label: 起点家具标签关键词
        target_label: 终点家具标签关键词

    Returns:
        PathAnalysis，动线分析结果
    """
    furniture_list = state.get("furniture_list", [])

    # 找到起点和终点
    source_node = None
    target_node = None
    for node in furniture_list:
        if source_label in node.get("label", ""):
            source_node = node
        if target_label in node.get("label", ""):
            target_node = node

    if not source_node or not target_node:
        return PathAnalysis(
            path_name=f"{source_label}→{target_label}",
            source_id=source_node["id"] if source_node else "",
            target_id=target_node["id"] if target_node else "",
            is_blocked=False,
        )

    # 计算直接路径上的最小净距
    blocking_objects: list[str] = []
    min_clearance = float("inf")

    for node in furniture_list:
        if node["id"] in (source_node["id"], target_node["id"]):
            continue

        # 计算该物体到路径的垂直距离
        # 简化处理：计算该物体到两个端点的距离
        result = calculate_edge_clearance(source_node, node)
        min_clearance = min(min_clearance, result.actual_clearance_mm)

        result = calculate_edge_clearance(target_node, node)
        min_clearance = min(min_clearance, result.actual_clearance_mm)

        # 如果净距小于轮椅通道，检查是否阻挡
        if min_clearance < CLEARANCE_STANDARDS["wheelchair_passage"].value_mm:
            blocking_objects.append(node["id"])

    return PathAnalysis(
        path_name=f"{source_node['label']}→{target_node['label']}",
        source_id=source_node["id"],
        target_id=target_node["id"],
        blocking_objects=blocking_objects,
        shortest_path_clearance_mm=min_clearance,
        is_blocked=len(blocking_objects) > 0 and min_clearance < CLEARANCE_STANDARDS["wheelchair_passage"].value_mm,
    )


def calculate_all_clearances(
    furniture_list: list[FurnitureNode],
) -> list[ClearanceResult]:
    """计算所有家具两两之间的边缘净距。

    Args:
        furniture_list: 家具节点列表

    Returns:
        净距计算结果列表
    """
    results: list[ClearanceResult] = []

    for i, node_a in enumerate(furniture_list):
        for node_b in furniture_list[i + 1:]:
            result = calculate_edge_clearance(node_a, node_b)
            results.append(result)

    return results


# ════════════════════════════════════════════════════════════════════════════════
# 规范碰撞检测
# ════════════════════════════════════════════════════════════════════════════════

def detect_violations(
    clearance_results: list[ClearanceResult],
    furniture_list: list[FurnitureNode],
    apply_strictest: bool = True,
) -> list[ViolationRecord]:
    """检测规范碰撞，识别违规项。

    Args:
        clearance_results: 净距计算结果
        furniture_list: 家具列表
        apply_strictest: 是否采用最严格解释原则（多规范冲突时取最大值）

    Returns:
        违规记录列表
    """
    violations: list[ViolationRecord] = []

    # 建立家具ID到节点的映射
    node_map: dict[str, FurnitureNode] = {node["id"]: node for node in furniture_list}

    for result in clearance_results:
        if result.actual_clearance_mm <= 0:
            # 物体重叠，视为严重违规
            violations.append(ViolationRecord(
                source_id=result.source_id,
                target_id=result.target_id,
                violation_type="overlap",
                actual_clearance_mm=0,
                required_clearance_mm=CLEARANCE_STANDARDS["wheelchair_passage"].value_mm,
                shortage_mm=CLEARANCE_STANDARDS["wheelchair_passage"].value_mm,
                regulation_ref=CLEARANCE_STANDARDS["wheelchair_passage"].regulation_ref,
                severity="high",
                description="两物体存在重叠，无法通行",
            ))
            continue

        # 检查轮椅通道净距 (900mm)
        required = CLEARANCE_STANDARDS["wheelchair_passage"].value_mm
        if result.actual_clearance_mm < required:
            severity = "high" if result.actual_clearance_mm < required * 0.5 else "medium"
            violations.append(ViolationRecord(
                source_id=result.source_id,
                target_id=result.target_id,
                violation_type="wheelchair_passage",
                actual_clearance_mm=result.actual_clearance_mm,
                required_clearance_mm=required,
                shortage_mm=required - result.actual_clearance_mm,
                regulation_ref=CLEARANCE_STANDARDS["wheelchair_passage"].regulation_ref,
                severity=severity,
                description=f"轮椅通道净距不足：实测{result.actual_clearance_mm:.0f}mm < 规范{required}mm",
            ))

    return violations


# ════════════════════════════════════════════════════════════════════════════════
# Agent 3: 无障碍设计审核员
# ════════════════════════════════════════════════════════════════════════════════

AGENT_3_PROMPT = """【角色】国家注册无障碍设计审核员

【职责】依据《GB 50763-2012 无障碍设计规范》等国家标准，对空间布局进行严格审核。

【执行逻辑 — 思维链 (Chain-of-Thought)】

## 步骤1: 数据摄入
读取所有家具的几何数据：
- 中心点坐标 (x, y)
- 尺寸 (width, depth, height)
- 预设最小安全净距

## 步骤2: 距离计算
执行几何函数计算边缘净距：
- dx = |cx_b - cx_a| - half_w_a - half_w_b
- dy = |cy_b - cy_a| - half_d_a - half_d_b
- clearance = min(max(0, dx), max(0, dy))

## 步骤3: 规范碰撞检测
调取 GB 规范条款进行核对：

| 净距类型 | 最小值 | GB条款 |
|----------|--------|--------|
| 轮椅通道净宽 | 900mm | GB 50763-2012 3.4.1 |
| 轮椅回转空间 | 1500mm | GB 50763-2012 3.5.3 |
| 门侧净距 | 800mm | GB 50763-2012 3.6.2 |
| 床侧净距 | 800mm | GB 50763-2012 4.4.3 |
| 马桶侧净距 | 600mm | GB 50763-2012 4.4.5 |
| 门槛高度 | 20mm | GB 50763-2012 3.6.1 |

## 步骤4: 动线审查
关键动线检测：
- 床 → 卫生间的最短路径是否被阻挡
- 门 → 床的最短路径是否被阻挡
- 轮椅旋转空间是否满足 1500mm 直径

【约束 — 最严格解释原则】
1. 当多项规范冲突时，取最大安全净距
2. 防火等级判定取最高等级
3. 必须引用具体 GB 条款编号
4. 无法确认的尺寸采用保守估计（偏小值）

【输出格式 — 审核报告】
{{
  "audit_metadata": {{
    "auditor_role": "国家注册无障碍设计审核员",
    "audit_timestamp": "ISO时间戳",
    "room_type": "房间类型",
    "furniture_count": 家具数量,
    "standard_applied": "GB 50763-2012"
  }},
  "clearance_matrix": [
    {{
      "source_id": "sofa_1",
      "target_id": "coffee_table_1",
      "actual_clearance_mm": 450,
      "required_clearance_mm": 900,
      "pass": false
    }}
  ],
  "violations": [
    {{
      "violation_id": "V001",
      "source_id": "sofa_1",
      "target_id": "coffee_table_1",
      "violation_type": "wheelchair_passage",
      "actual_clearance_mm": 450,
      "required_clearance_mm": 900,
      "shortage_mm": 450,
      "regulation_ref": "GB 50763-2012 3.4.1",
      "severity": "high",
      "description": "轮椅通道净距严重不足"
    }}
  ],
  "path_analysis": [
    {{
      "path_name": "床→卫生间",
      "source_id": "bed_1",
      "target_id": "toilet_1",
      "blocking_objects": ["chair_1"],
      "shortest_path_clearance_mm": 350,
      "is_blocked": true,
      "regulation_ref": "GB 50763-2012 4.4.3"
    }}
  ],
  "summary": {{
    "total_violations": 3,
    "high_severity": 1,
    "medium_severity": 1,
    "low_severity": 1,
    "overall_compliance": "不合格",
    "recommendation": "建议调整家具布局"
  }}
}}

【规范依据】
{CHINESE_REGULATION_SYSTEM_RULES}"""


def agent_3_audit_topology(state: GraphState) -> dict[str, Any]:
    """Agent 3: 无障碍设计审核 — 基于拓扑矩阵和规范检测。

    Args:
        state: GraphState

    Returns:
        审核报告 dict
    """
    furniture_list = state.get("furniture_list", [])
    room_type = state.get("room_type", "未知")

    # 步骤1: 计算所有净距
    clearance_results = calculate_all_clearances(furniture_list)

    # 步骤2: 检测违规
    violations = detect_violations(clearance_results, furniture_list)

    # 步骤3: 动线分析
    path_analyses: list[PathAnalysis] = []

    # 关键动线检测
    critical_paths = [
        ("床", "卫生间"),
        ("床", "门"),
        ("沙发", "卫生间"),
        ("轮椅", "卫生间"),
    ]

    for source_label, target_label in critical_paths:
        analysis = calculate_path_blocking(state, source_label, target_label)
        if analysis.source_id and analysis.target_id:
            path_analyses.append(analysis)

    # 构建审核报告
    violation_records = []
    for i, v in enumerate(violations):
        violation_records.append({
            "violation_id": f"V{str(i + 1).zfill(3)}",
            "source_id": v.source_id,
            "target_id": v.target_id,
            "violation_type": v.violation_type,
            "actual_clearance_mm": round(v.actual_clearance_mm, 1),
            "required_clearance_mm": round(v.required_clearance_mm, 1),
            "shortage_mm": round(v.shortage_mm, 1),
            "regulation_ref": v.regulation_ref,
            "severity": v.severity,
            "description": v.description,
        })

    clearance_matrix = [
        {
            "source_id": r.source_id,
            "target_id": r.target_id,
            "actual_clearance_mm": round(r.actual_clearance_mm, 1),
            "required_clearance_mm": CLEARANCE_STANDARDS["wheelchair_passage"].value_mm,
            "pass": r.actual_clearance_mm >= CLEARANCE_STANDARDS["wheelchair_passage"].value_mm,
        }
        for r in clearance_results
    ]

    path_analysis_records = [
        {
            "path_name": p.path_name,
            "source_id": p.source_id,
            "target_id": p.target_id,
            "blocking_objects": p.blocking_objects,
            "shortest_path_clearance_mm": round(p.shortest_path_clearance_mm, 1),
            "is_blocked": p.is_blocked,
            "regulation_ref": CLEARANCE_STANDARDS["wheelchair_passage"].regulation_ref,
        }
        for p in path_analyses
    ]

    # 统计
    high_severity = sum(1 for v in violations if v.severity == "high")
    medium_severity = sum(1 for v in violations if v.severity == "medium")
    low_severity = sum(1 for v in violations if v.severity == "low")

    overall_compliance = "合格" if len(violations) == 0 else (
        "严重不合格" if high_severity > 0 else "不合格"
    )

    return {
        "audit_metadata": {
            "auditor_role": "国家注册无障碍设计审核员",
            "room_type": room_type,
            "furniture_count": len(furniture_list),
            "standard_applied": "GB 50763-2012",
        },
        "clearance_matrix": clearance_matrix,
        "violations": violation_records,
        "path_analysis": path_analysis_records,
        "summary": {
            "total_violations": len(violations),
            "high_severity": high_severity,
            "medium_severity": medium_severity,
            "low_severity": low_severity,
            "overall_compliance": overall_compliance,
            "recommendation": "建议调整家具布局" if len(violations) > 0 else "空间布局符合无障碍设计规范",
        },
    }


def generate_final_report(state: GraphState, audit_result: dict[str, Any]) -> str:
    """综合拓扑和规范审核结果，生成最终报告。

    Args:
        state: GraphState
        audit_result: Agent 3 审核结果

    Returns:
        面向用户的安全报告（口语化）
    """
    furniture_list = state.get("furniture_list", [])
    violations = audit_result.get("violations", [])
    path_analysis = audit_result.get("path_analysis", [])
    summary = audit_result.get("summary", {})

    lines = []
    lines.append("=" * 50)
    lines.append("适老化安全审核报告")
    lines.append("=" * 50)
    lines.append("")

    # 风险等级
    risk_level = "高风险" if summary.get("high_severity", 0) > 0 else (
        "中风险" if summary.get("medium_severity", 0) > 0 else (
        "低风险" if summary.get("low_severity", 0) > 0 else "安全"
    ))

    lines.append(f"【综合风险等级】{risk_level}")
    lines.append(f"发现 {summary.get('total_violations', 0)} 项违规，其中：")
    lines.append(f"  - 严重违规: {summary.get('high_severity', 0)} 项")
    lines.append(f"  - 中度违规: {summary.get('medium_severity', 0)} 项")
    lines.append(f"  - 轻微违规: {summary.get('low_severity', 0)} 项")
    lines.append("")

    # 违规详情
    if violations:
        lines.append("【违规详情】")
        for v in violations:
            lines.append(f"  {v['violation_id']}: {v['description']}")
            lines.append(f"    实测净距: {v['actual_clearance_mm']:.0f}mm (规范要求: {v['required_clearance_mm']}mm)")
            lines.append(f"    短缺量: {v['shortage_mm']:.0f}mm")
            lines.append(f"    依据: 《{v['regulation_ref']}》")
            lines.append("")
        lines.append("")

    # 动线分析
    blocked_paths = [p for p in path_analysis if p.get("is_blocked")]
    if blocked_paths:
        lines.append("【受阻动线】")
        for p in blocked_paths:
            lines.append(f"  {p['path_name']}: 被 {', '.join(p['blocking_objects'])} 阻挡")
            lines.append(f"    最短路径净距: {p['shortest_path_clearance_mm']:.0f}mm")
            lines.append("")

    # 建议
    lines.append("【改进建议】")
    if summary.get("total_violations", 0) > 0:
        lines.append("  1. 将轮椅通道区域的杂物进行清理")
        lines.append("  2. 确保主要通道净宽不小于 900mm")
        lines.append("  3. 保持床侧、门侧有足够的起身空间")
    else:
        lines.append("  空间布局符合无障碍设计规范，建议保持现状。")

    lines.append("")
    lines.append("=" * 50)

    return "\n".join(lines)
