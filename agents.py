"""Multi-Agent Collaboration System — LangGraph StateGraph Implementation.

【架构核心约束】
1. 禁止落盘缓存: 全程 TypedDict 内存流转
2. 二次剪裁 (Pass 2): Agent 1 → Crop → Agent 2 并发分析
3. 坐标系锁定: 几何中心点 (x,y)，单位毫米

【代理分工】
- Agent 1 (VisionExtractor): 从图像提取 BBox、尺寸、位置
- Agent 2 (ComplianceAuditor): 对裁剪局部图进行材质/安全合规分析
- Agent 3 (ReportGenerator): 综合拓扑与合规结果生成报告
"""

from __future__ import annotations

import os
from typing import Any

from langgraph.graph import StateGraph, END

from models import (
    GraphState,
    FurnitureNode,
    TopologyEdge,
    create_initial_state,
    generate_furniture_id,
)


# ════════════════════════════════════════════════════════════════════════════════
# Agent 1: Vision Extractor
# 职责: 从图像提取 BBox，返回 furniture_list (待 Agent 2 填写 pass_2_audit)
# ════════════════════════════════════════════════════════════════════════════════

AGENT_1_SYSTEM_PROMPT = """【角色】资深建筑测绘工程师

【任务】从房间图像中提取所有可见家具的几何信息。

【坐标系统 — 强制约束】
- 原点 (0,0) = 房间左下角（俯视图）
- X轴正向 = 向右
- Y轴正向 = 向上
- 所有尺寸单位 = 毫米 (mm)
- 位置 = 物体【几何中心点】坐标

【输出格式】仅输出 JSON，禁止解释：

{
  "boundary": {
    "width_mm": 房间宽度,
    "depth_mm": 房间深度,
    "doors": [{"x": 中心X, "y": 中心Y, "width": 门宽, "height": 门高, "opens_to": "内开/外开"}],
    "windows": [{"x": 中心X, "y": 窗台Y, "width": 窗宽, "height": 窗高}]
  },
  "furniture": [
    {
      "id": "sofa_1",
      "label": "沙发",
      "center": [x坐标, y坐标],
      "size": [宽度, 深度, 高度],
      "rotation": 0.0,
      "bbox": [left_px, top_px, right_px, bottom_px],
      "material": "布艺/木质/金属",
      "is_obstacle": false
    }
  ]
}

【校准】无显式校准时使用默认参照物估算比例尺。"""


def agent_1_extract_vision(state: GraphState) -> GraphState:
    """Agent 1: 视觉提取 - 从图像提取 BBox 和几何信息。

    【注意】此函数仅为框架定义，实际 VLM 调用在 vision_engine.py 中实现。
    本函数接收 state，返回更新后的 state。
    """
    # TODO (后续细节调整): 实现 VLM 调用逻辑
    # - 调用智谱 GLM-4.6V
    # - 解析 JSON 响应
    # - 填充 furniture_list 和 boundary
    # - 返回更新后的 state

    return state


# ════════════════════════════════════════════════════════════════════════════════
# Agent 2: Compliance Auditor
# 职责: 对每个家具的局部裁剪图进行材质/安全合规分析
# ════════════════════════════════════════════════════════════════════════════════

AGENT_2_SYSTEM_PROMPT = """【角色】适老化安全审查专家

【任务】分析局部裁剪图像，评估家具的适老化安全合规性。

【评估维度】
1. 材质安全性: 表面是否光滑？是否有尖锐边角？
2. 高度合理性: 座椅高度是否适合老人起身？
3. 稳定性评估: 家具是否稳固？是否有倾倒风险？
4. 通道净距: 与相邻家具的间距是否满足轮椅通行（≥900mm）？

【输出格式】JSON:
{
  "furniture_id": "sofa_1",
  "compliance_result": {
    "material_safe": true/false,
    "height_appropriate": true/false,
    "stability_safe": true/false,
    "clearance_adequate": true/false,
    "issues": ["具体问题描述"],
    "severity": "high/medium/low"
  },
  "recommendations": ["改进建议"]
}

【规范依据】GB 50763《无障碍设计规范》、GB 50222《建筑内部装修设计防火规范》"""


def agent_2_audit_compliance(state: GraphState) -> GraphState:
    """Agent 2: 合规审计 - 对裁剪局部图进行材质/安全分析。

    【注意】此函数仅为框架定义。
    - 接收 crop_image_base64 和 crop_metadata（已在 image_processor.py 中生成）
    - 对每个家具调用 VLM 分析
    - 填写 FurnitureNode.pass_2_audit 字段
    """
    # TODO (后续细节调整):
    # 1. 从 state['crop_image_base64'] 获取裁剪图
    # 2. 从 state['crop_metadata'] 获取尺寸数据
    # 3. 并发调用 VLM 对每件家具进行分析
    # 4. 更新 furniture_list 中对应节点的 pass_2_audit 字段
    # 5. 返回更新后的 state

    return state


# ════════════════════════════════════════════════════════════════════════════════
# Agent 3: Report Generator
# 职责: 综合拓扑计算结果和 Agent 2 审计结果，生成最终报告
# ════════════════════════════════════════════════════════════════════════════════

AGENT_3_SYSTEM_PROMPT = """【角色】适老化改造顾问

【任务】综合空间拓扑和合规审计结果，生成面向老年人的安全报告。

【输出原则】
- 口语化，像邻居家的装修老师傅在说话
- 每条建议都要说清楚"对老人有什么好处"
- 禁止出现技术术语（坐标、JSON、参数等）
- 规范引用使用全称（如《中国建筑无障碍设计规范》）

【报告结构】
1. 综合风险等级（高/中/低）
2. 主要安全隐患（按严重程度排序）
3. 适老化改造建议（家具布局调整 + 环境改进）
4. 未覆盖区域提醒"""


def agent_3_generate_report(state: GraphState) -> GraphState:
    """Agent 3: 报告生成 - 综合拓扑和合规结果生成最终报告。

    【注意】此函数仅为框架定义。
    - 读取 state['topology_matrix'] 和 state['furniture_list']
    - 综合风险评估
    - 生成面向用户的口语化报告
    """
    # TODO (后续细节调整):
    # 1. 遍历 furniture_list，收集所有 pass_2_audit 结果
    # 2. 基于 topology_matrix 计算通道净距风险
    # 3. 综合评估 risk_level
    # 4. 生成 final_report
    # 5. 返回更新后的 state

    return state


# ════════════════════════════════════════════════════════════════════════════════
# 拓扑计算节点
# ════════════════════════════════════════════════════════════════════════════════

def calculate_topology(state: GraphState) -> GraphState:
    """计算家具间的拓扑关系和边缘净距。

    基于几何中心点坐标计算：
    - 两物件间的最小边缘净距
    - 判断是否存在通行障碍
    - 生成 topology_matrix
    """
    furniture_list = state.get("furniture_list", [])
    topology_matrix: dict[str, dict[str, TopologyEdge]] = {}

    for i, node_a in enumerate(furniture_list):
        topology_matrix[node_a["id"]] = {}
        cx_a, cy_a = node_a["center"]
        w_a, d_a, _ = node_a["size"]

        for j, node_b in enumerate(furniture_list):
            if i >= j:
                continue

            cx_b, cy_b = node_b["center"]
            w_b, d_b, _ = node_b["size"]

            # 计算边缘净距（假设未旋转的轴对齐矩形）
            half_w_a, half_d_a = w_a / 2, d_a / 2
            half_w_b, half_d_b = w_b / 2, d_b / 2

            dx = abs(cx_b - cx_a) - half_w_a - half_w_b
            dy = abs(cy_b - cy_a) - half_d_a - half_d_b

            # 最小净距
            clearance = max(0, min(dx if dx > 0 else 0, dy if dy > 0 else 0))

            # 判断关系类型
            if clearance <= 0:
                relationship: str = "adjacent_to"
            elif dx > dy:
                relationship = "beside_left" if cx_b < cx_a else "beside_right"
            else:
                relationship = "near"

            if clearance < 900 and clearance > 0:
                relationship = "blocks_access_to"

            edge: TopologyEdge = {
                "source_id": node_a["id"],
                "target_id": node_b["id"],
                "clearance_mm": clearance,
                "relationship": relationship,
            }

            topology_matrix[node_a["id"]][node_b["id"]] = edge

    state["topology_matrix"] = topology_matrix
    return state


# ════════════════════════════════════════════════════════════════════════════════
# LangGraph StateGraph 定义 (含 Validator Node)
# ════════════════════════════════════════════════════════════════════════════════

def create_compliance_graph() -> StateGraph:
    """创建适老化合规审查的 LangGraph (含 Validator Node)。

    数据流:
    ┌─────────────┐
    │   START     │
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │ agent_1     │ ← 图像输入
    │ extract     │
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │ validator_1 │ ← 校验 Agent 1 输出
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │ crop_images │ ← 二次剪裁（后端执行）
    │ (后台处理)  │
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │ agent_2     │ ← 局部图 + 尺寸数据
    │ audit       │   (并发分析)
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │ validator_2 │ ← 校验 Agent 2 输出
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │ topology    │ ← 计算边缘净距
    │ calculate   │
    └──────┬─────┘
           ▼
    ┌─────────────┐
    │ validator_3 │ ← 校验拓扑矩阵
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │ agent_3     │
    │ report      │ ← 生成最终报告
    └──────┬──────┘
           ▼
        ┌──────┐
        │ END  │
        └──────┘

    校验失败处理:
    - fatal 错误 → 抛出异常，终止流程
    - warning → 记录日志，继续执行
    """
    from validator import validate_state, ValidationStrategy, format_validation_report
    import logging

    logger = logging.getLogger("agents")

    def _validator_node(state: GraphState, node_name: str) -> GraphState:
        """Validator Node 实现"""
        result = validate_state(state, node_name)
        action = ValidationStrategy.get_action(result)

        # 记录校验结果
        report = format_validation_report(result)
        logger.info(f"Validator after {node_name}:\n{report}")

        # 存储校验结果到 state
        if "validation_history" not in state:
            state["validation_history"] = []
        state["validation_history"].append({
            "after_node": node_name,
            "is_valid": result.is_valid,
            "passed": result.checks_passed,
            "failed": result.checks_failed,
            "warnings": result.warnings,
            "action": action,
        })

        # fatal 错误 → 抛出异常
        if action == "retry_agent":
            failed_checks = ", ".join(result.checks_failed)
            raise ValueError(
                f"Fatal validation error after {node_name}: {failed_checks}"
            )

        return state

    workflow = StateGraph(GraphState)

    # 添加 Agent 节点
    workflow.add_node("agent_1_extract", agent_1_extract_vision)
    workflow.add_node("agent_2_audit", agent_2_audit_compliance)
    workflow.add_node("topology_calculate", calculate_topology)
    workflow.add_node("agent_3_report", agent_3_generate_report)

    # 添加 Validator 节点 (使用 partial 绑定 node_name)
    from functools import partial
    workflow.add_node("validator_1", partial(_validator_node, node_name="agent_1_extract"))
    workflow.add_node("validator_2", partial(_validator_node, node_name="agent_2_audit"))
    workflow.add_node("validator_3", partial(_validator_node, node_name="topology_calculate"))

    # 定义边
    workflow.set_entry_point("agent_1_extract")

    # agent_1 → validator_1 → crop → agent_2 → validator_2 → topology → validator_3 → agent_3 → END
    workflow.add_edge("agent_1_extract", "validator_1")
    workflow.add_edge("validator_1", "agent_2_audit")
    workflow.add_edge("agent_2_audit", "validator_2")
    workflow.add_edge("validator_2", "topology_calculate")
    workflow.add_edge("topology_calculate", "validator_3")
    workflow.add_edge("validator_3", "agent_3_report")
    workflow.add_edge("agent_3_report", END)

    return workflow.compile()


# ════════════════════════════════════════════════════════════════════════════════
# 便捷入口函数
# ════════════════════════════════════════════════════════════════════════════════

def run_compliance_analysis(
    image_paths: list[str],
    room_type: str = "客厅",
    calibration: dict[str, Any] | None = None,
) -> GraphState:
    """运行完整的适老化合规审查流程。

    Args:
        image_paths: 图像文件路径列表
        room_type: 房间类型
        calibration: 比例尺校准数据

    Returns:
        最终的 GraphState（包含 final_report）
    """
    state = create_initial_state(
        session_id=None,
        room_type=room_type,
        image_paths=image_paths,
    )
    if calibration:
        state["scale_calibration"] = calibration

    graph = create_compliance_graph()
    result = graph.invoke(state)
    return result
