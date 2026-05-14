"""房间视觉分析模块 — Multi-Agent 架构专用版本。

【架构约束】
- 禁止落盘缓存: 所有数据通过 TypedDict 内存流转
- 坐标系锁定: 几何中心点 (x, y)，单位毫米
- 二次剪裁 (Pass 2): Agent 1 → Crop → Agent 2

【模块职责】
- Agent 1: 空间拓扑提取器 (BBox 提取)
- Agent 2: 合规审计员 (局部裁剪图分析)
- 强力解析器: 从混乱输出中提取 JSON

【已废弃】(Legacy 代码已移除)
- analyze_room_image / analyze_room_images (旧架构)
- SYSTEM_PROMPT / SCENE_PROMPT / SCENE_MULTI_PROMPT (旧架构)
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import json
import logging
import os
import re as _re
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from zhipuai import ZhipuAI

from cn_regulation_rules import CHINESE_REGULATION_SYSTEM_RULES
from models import (
    GraphState,
    FurnitureNode,
    RoomBoundaryInfo,
    generate_furniture_id,
)


# ════════════════════════════════════════════════════════════════════════════════
# 常量定义
# ════════════════════════════════════════════════════════════════════════════════

MODEL_VISION = "glm-4v"  # 统一使用小写模型名

logger = logging.getLogger("vision_engine")


# ════════════════════════════════════════════════════════════════════════════════
# Agent 1: 空间拓扑提取器
# ════════════════════════════════════════════════════════════════════════════════

AGENT_1_PROMPT = """【角色】资深建筑测绘工程师

【任务】从房间图像中提取所有可见家具的几何信息，构建 2D 平面坐标系统。

【坐标系统 — 强制约束】
- 原点 (0,0) = 房间左下角（俯视图）
- X轴正向 = 向右
- Y轴正向 = 向上
- Z轴 = 离地高度（用于插座/桌面高度）
- 所有尺寸单位 = 毫米 (mm)
- 位置 = 物体【几何中心点】坐标

【重要】你是测绘员，不是安全员：
- 只负责提取【精确的几何数据】
- 不要判断是否是障碍物（那是后续 Agent 2 的工作）
- 关注：表面材质类型、预估摩擦系数（friction_level）

【输出格式】将结果包裹在 <result></result> XML 标签之间，禁止输出任何解释：

<result>
{{
  "boundary": {{
    "width_mm": 房间宽度(毫米),
    "depth_mm": 房间深度(毫米),
    "doors": [
      {{"x": 中心X坐标, "y": 中心Y坐标, "width": 门宽, "height": 门高, "opens_to": "内开/外开"}}
    ],
    "windows": [
      {{"x": 中心X坐标, "y": 窗台Y坐标, "width": 窗宽, "height": 窗高}}
    ]
  }},
  "furniture": [
    {{
      "id": "sofa_1",
      "label": "沙发",
      "center": [x坐标(毫米), y坐标(毫米)],
      "elevation_mm": 离地高度(毫米, 地板物体填0),
      "size": [宽度(毫米), 深度(毫米), 高度(毫米)],
      "rotation": 0.0,
      "bbox": [left_px, top_px, right_px, bottom_px],
      "material": "布艺/木质/金属/玻璃",
      "friction_level": "high/medium/low (表面摩擦程度预估)"
    }}
  ]
}}
</result>

【校准规则】
{calibration_instruction}"""


# ════════════════════════════════════════════════════════════════════════════════
# Agent 2: 合规审计员 (适老化产品工业设计师与质检员)
# 思维链模式 (Chain-of-Thought)
# ════════════════════════════════════════════════════════════════════════════════

AGENT_2_PROMPT = """【角色】适老化产品工业设计师与质检员

【任务】针对单件家具局部图像，提取微观物理特征，识别潜在安全风险。

【上下文信息】
- 物件ID: {furniture_id}
- 家具名称: {furniture_name}
- 几何中心点: ({center_x}mm, {center_y}mm)
- 离地高度: {elevation}mm
- 尺寸: 宽{width}mm × 深{depth}mm × 高{height}mm
- 主要材质: {material}

【执行逻辑 — 思维链 (Chain-of-Thought)】

## 步骤1: 材质预估
仔细观察表面材质，评估以下指标：

a) 材质类型识别：
   - 高光瓷砖 → 反光率高，湿滑风险高
   - 哑光木皮 → 反光率低，摩擦系数适中
   - 皮革 → 表面光滑，液体渗透后极滑
   - 布艺/织物 → 摩擦系数高，但可能积灰
   - 玻璃 → 高反光+透明，误导视弱老人对距离的判断

b) 摩擦系数评估：
   - high: 粗糙表面、毛毡、防滑纹理
   - medium: 哑光木、金属拉丝
   - low: 光滑瓷砖、玻璃、抛光石材

c) 二次风险识别：
   - 玻璃反光 → 误导老人对深度的判断
   - 光滑金属 → 冬季冰凉触感导致躲避反应
   - 反光地板 → 强光下形成"水坑"错觉

## 步骤2: 几何测算
寻找边缘特征，利用参照物（插座高度86mm）预估尺度：

a) 边缘类型识别：
   - 锐角 (R<3mm) → 极高危，划伤风险
   - 直角 (R=3-10mm) → 高危，撞击伤害
   - 安全倒角 (R≥10mm) → 低风险，符合规范

b) 倒角半径预估：
   - 寻找已知尺寸参照物（插座86mm）
   - 比较边缘弯曲程度与参照物比例
   - 若无法确认是否倒角 → 默认判定为"存在锐角风险"

c) 突出物检测：
   - 门把手外露角度
   - 铰链突出量
   - 装饰性尖角

## 步骤3: 人机工学评估
针对座椅/床类家具：

a) 座面高度检测：
   - 标准适老化高度: 400-500mm
   - 过低 (<400mm) → 起身需大腿发力，老人腿部力量不足
   - 过高 (>500mm) → 脚悬空，坐不稳易滑落

b) 扶手支撑性：
   - 扶手高度是否在 650-750mm（便于借力）
   - 扶手是否前凸（方便站起时抓握）

c) 床垫/坐垫硬度：
   - 过软 → 起身困难，缺乏支撑
   - 过硬 → 不舒适，压疮风险

【约束 — 极其挑剔原则】
1. 若无法确认是否倒角，默认判定为"存在锐角风险"
2. 玻璃/高光材质必须标注"反光误导风险"
3. 低于 400mm 的座椅高度直接判定为"高危"
4. 所有判断必须基于图像证据，无证据则标注"无法确认-存疑"

【输出格式 — 微观特征报告】
{{
  "furniture_id": "{furniture_id}",
  "micro_features": {{
    "material_analysis": {{
      "primary_material": "材质类型",
      "friction_coefficient": "high/medium/low",
      "gloss_level": "high/medium/low (光泽度)",
      "secondary_risks": ["二次风险列表"],
      "evidence_description": "材质识别依据描述"
    }},
    "geometry_analysis": {{
      "corner_type": "锐角/直角/安全倒角/无法确认",
      "r_corner_radius_mm": "预估倒角半径，若无法确认填 -1",
      "sharp_protrusions": ["突出物列表"],
      "edge_condition": "边缘状态描述",
      "reference_calibration": "参照物校准说明"
    }},
    "ergonomics_analysis": {{
      "seat_height_mm": "实测/估算座高，若不适用填 null",
      "seat_height_compliant": "true/false/null (是否符合 400-500mm)",
      "armrest_present": true/false,
      "armrest_height_mm": "扶手高度，若无填 null",
      "lumbar_support": "有/无/无法确认",
      "sitting_stability": "稳定/不稳/无法确认"
    }}
  }},
  "physical_risk_points": [
    {{
      "risk_id": 1,
      "category": "材质/几何/人机",
      "severity": "high/medium/low",
      "description": "风险描述",
      "evidence": "图像证据",
      "recommendation": "改进建议"
    }}
  ],
  "summary": "[物件ID] - [材质特征] - [几何特征] - [物理风险点]",
  "confidence": "high/medium/low (判断置信度)"
}}

【规范依据】
{regulation_rules}"""


# ════════════════════════════════════════════════════════════════════════════════
# 强力解析器 — 从混乱输出中提取 JSON
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
        cleaned = text.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            errors.append(f"[{label}] json.loads 失败: {exc}")
            return None

    # 策略 1: XML 标签 <result>...</result>
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

    # 策略 2: 去掉 ```json 代码块
    lines = raw_text.strip().split("\n")
    in_block = False
    block_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```json") and not in_block:
            in_block = True
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

    # 策略 3: 去掉普通 ``` 代码块
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

    # 策略 4: 第一个 { 到最后一个 }
    stripped = raw_text.strip()
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = stripped[first_brace : last_brace + 1]
        result = _try_parse(candidate, "首{末}")
        if result is not None:
            return result
        candidates.append(f"首{{末}}内容前200字符: {candidate[:200]!r}")

    # 策略 5: 逐字符栈解析
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
                    last_valid = candidate

        if last_valid:
            candidates.append(f"栈解析最近候选前200字符: {last_valid[:200]!r}")

    # 所有策略均失败
    all_errors = "\n".join(errors) if errors else "(无)"
    all_candidates = "\n\n".join(candidates) if candidates else "(无候选)"
    raise ValueError(
        f"所有解析策略均失败。\n"
        f"原始文本前500字符：{raw_text[:500]!r}\n\n"
        f"解析错误：\n{all_errors}\n\n"
        f"候选片段：\n{all_candidates}"
    )


# ════════════════════════════════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════════════════════════════════

def _load_image_base64(image_path: str) -> str:
    """加载图片并返回 base64 编码字符串（不含 data URI 前缀）。"""
    path = Path(image_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"图片文件不存在: {path}")
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _create_client() -> ZhipuAI:
    """创建智谱 AI 客户端。"""
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key:
        raise EnvironmentError("ZHIPUAI_API_KEY 未设置。")
    return ZhipuAI(api_key=api_key)


def _build_calibration_instruction(
    ref_object: str | None,
    ref_size_mm: float | None,
) -> str:
    """构建比例尺校准指令。"""
    if ref_object and ref_size_mm and ref_size_mm > 0:
        return (
            f"★ 比例尺约束：已知参照物「{ref_object}」的实际尺寸为 {ref_size_mm:.0f}mm。"
            f"以此为唯一标准，所有坐标和尺寸必须与此比例尺一致。"
        )
    return (
        "★ 比例尺约束（无显式校准）：以成年人身高约 1700mm 为高度参照，"
        "以标准门宽 900mm、常见瓷砖 300mm×300mm 为尺寸参照。"
        "标注「估算值」而非实测值。"
    )


def _call_vision(
    client: ZhipuAI,
    image_base64: str,
    prompt: str,
    model: str = MODEL_VISION,
) -> str:
    """调用视觉模型，返回文本响应。"""
    data_uri = f"data:image/jpeg;base64,{image_base64}"

    response = client.chat.completions.create(
        model=model,
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
        raise RuntimeError(f"GLM-4V 返回了空内容。model={model}")
    return content


def _call_vision_no_image(
    client: ZhipuAI,
    prompt: str,
    model: str = MODEL_VISION,
) -> str:
    """调用视觉模型（无图像，纯文本），返回文本响应。"""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": [{"type": "text", "text": prompt}]},
        ],
    )

    raw_msg = response.choices[0].message
    content = raw_msg.content or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return content


# ════════════════════════════════════════════════════════════════════════════════
# Agent 1: 空间拓扑提取
# ════════════════════════════════════════════════════════════════════════════════

def agent_1_extract(
    image_path: str,
    calibration_data: dict | None = None,
) -> GraphState:
    """Agent 1: 从图像提取 BBox，输出 GraphState。

    Args:
        image_path: 图片文件路径
        calibration_data: 校准数据 {"ref_object": str, "ref_size_mm": float}

    Returns:
        GraphState，包含 furniture_list 和 boundary

    Raises:
        FileNotFoundError: 图片文件不存在
        ValueError: 图片非房间场景
        RuntimeError: 解析失败
    """
    cal = dict(calibration_data) if calibration_data else {}
    ref_object = cal.get("ref_object") or None
    ref_size_mm = cal.get("ref_size_mm")
    if ref_size_mm is not None:
        ref_size_mm = float(ref_size_mm)

    calibration_instruction = _build_calibration_instruction(ref_object, ref_size_mm)

    client = _create_client()
    image_b64 = _load_image_base64(image_path)

    prompt = AGENT_1_PROMPT.format(calibration_instruction=calibration_instruction)
    content = _call_vision(client, image_b64, prompt)

    # 解析 JSON
    try:
        payload = extract_json_from_thinking_model(content)
    except ValueError as exc:
        raise RuntimeError(f"无法解析 Agent 1 响应: {exc}") from exc

    # 转换为 GraphState
    boundary_data = payload.get("boundary", {})
    furniture_data = payload.get("furniture", [])

    furniture_list: list[FurnitureNode] = []
    for idx, item in enumerate(furniture_data if isinstance(furniture_data, list) else []):
        if not isinstance(item, dict):
            continue

        center_list = item.get("center", [0, 0])
        size_list = item.get("size", [100, 100, 100])
        bbox_list = item.get("bbox", [0, 0, 100, 100])

        furniture_list.append(
            FurnitureNode(
                id=item.get("id") or generate_furniture_id(item.get("label", "item"), idx + 1),
                label=item.get("label", "未知物品"),
                center=(
                    float(center_list[0]) if len(center_list) >= 1 else 0.0,
                    float(center_list[1]) if len(center_list) >= 2 else 0.0,
                ),
                elevation_mm=float(item.get("elevation_mm", 0)),
                size=(
                    float(size_list[0]) if len(size_list) >= 1 else 100.0,
                    float(size_list[1]) if len(size_list) >= 2 else 100.0,
                    float(size_list[2]) if len(size_list) >= 3 else 100.0,
                ),
                rotation=float(item.get("rotation", 0.0)),
                bbox=(
                    int(bbox_list[0]) if len(bbox_list) >= 1 else 0,
                    int(bbox_list[1]) if len(bbox_list) >= 2 else 0,
                    int(bbox_list[2]) if len(bbox_list) >= 3 else 0,
                    int(bbox_list[3]) if len(bbox_list) >= 4 else 0,
                ),
                material=item.get("material", "未知材质"),
                friction_level=item.get("friction_level", "medium"),
                is_obstacle=False,  # Agent 1 不判断，Agent 2 决定
                pass_2_audit="",  # 待 Agent 2 填写
            )
        )

    boundary = RoomBoundaryInfo(
        width_mm=float(boundary_data.get("width_mm", 0)),
        depth_mm=float(boundary_data.get("depth_mm", 0)),
        walls=[],
        doors=[
            {
                "x": float(d.get("x", 0)),
                "y": float(d.get("y", 0)),
                "width": float(d.get("width", 0)),
                "height": float(d.get("height", 0)),
                "opens_to": d.get("opens_to", "未知"),
            }
            for d in boundary_data.get("doors", [])
            if isinstance(d, dict)
        ],
        windows=[
            {
                "x": float(w.get("x", 0)),
                "y": float(w.get("y", 0)),
                "width": float(w.get("width", 0)),
                "height": float(w.get("height", 0)),
            }
            for w in boundary_data.get("windows", [])
            if isinstance(w, dict)
        ],
    )

    state = GraphState(
        session_id=cal.get("session_id", ""),
        room_type=cal.get("room_type", "客厅"),
        image_paths=[image_path],
        scale_calibration=cal,
        furniture_list=furniture_list,
        boundary=boundary,
        raw_vision_response=content,
        topology_matrix={},
        final_report="",
        risk_level="unknown",
    )

    return state


# ════════════════════════════════════════════════════════════════════════════════
# Agent 2: 合规审计 (单件 + 异步批处理)
# ════════════════════════════════════════════════════════════════════════════════

def agent_2_audit_single(
    crop_image_b64: str,
    furniture_node: FurnitureNode,
) -> dict[str, Any]:
    """Agent 2: 对单个家具的裁剪图进行微观特征提取与合规审计。

    基于思维链模式 (Chain-of-Thought) 执行：
    1. 材质预估：识别表面材质，评估摩擦系数和反光率
    2. 几何测算：寻找边缘特征，预估倒角半径
    3. 人机工学：评估座椅/床垫离地高度

    Args:
        crop_image_b64: 裁剪后的局部图像（Base64）
        furniture_node: 家具节点信息

    Returns:
        微观特征报告 dict
    """
    client = _create_client()
    center_x, center_y = furniture_node["center"]
    w, d, h = furniture_node["size"]

    prompt = AGENT_2_PROMPT.format(
        furniture_id=furniture_node["id"],
        furniture_name=furniture_node["label"],
        center_x=round(center_x, 1),
        center_y=round(center_y, 1),
        elevation=round(furniture_node.get("elevation_mm", 0), 1),
        width=round(w, 1),
        depth=round(d, 1),
        height=round(h, 1),
        material=furniture_node["material"],
        regulation_rules=CHINESE_REGULATION_SYSTEM_RULES,
    )

    content = _call_vision(client, crop_image_b64, prompt)

    try:
        result = extract_json_from_thinking_model(content)
        return result
    except ValueError:
        logger.warning(f"Agent 2 解析失败 furniture_id={furniture_node['id']}，返回默认值")
        return {
            "furniture_id": furniture_node["id"],
            "micro_features": {
                "material_analysis": {
                    "primary_material": "无法确认",
                    "friction_coefficient": "medium",
                    "gloss_level": "无法确认",
                    "secondary_risks": ["材质识别失败"],
                    "evidence_description": "图像解析异常",
                },
                "geometry_analysis": {
                    "corner_type": "无法确认",
                    "r_corner_radius_mm": -1,
                    "sharp_protrusions": [],
                    "edge_condition": "无法确认",
                    "reference_calibration": "解析异常",
                },
                "ergonomics_analysis": {
                    "seat_height_mm": None,
                    "seat_height_compliant": None,
                    "armrest_present": None,
                    "armrest_height_mm": None,
                    "lumbar_support": "无法确认",
                    "sitting_stability": "无法确认",
                },
            },
            "physical_risk_points": [
                {
                    "risk_id": 1,
                    "category": "系统",
                    "severity": "unknown",
                    "description": "微观特征提取失败",
                    "evidence": "VLM 响应解析异常",
                    "recommendation": "请重试或检查图像质量",
                },
            ],
            "summary": f"[{furniture_node['id']}] - [材质识别失败] - [几何识别失败] - [提取异常]",
            "confidence": "low",
        }


def agent_2_audit_batch(
    crop_images_b64: list[str],
    furniture_nodes: list[FurnitureNode],
) -> list[dict[str, Any]]:
    """Agent 2: 批量并发审计。

    使用 ThreadPoolExecutor 实现真正的并发 API 调用，
    避免顺序调用造成的延迟累积。

    Args:
        crop_images_b64: 裁剪图 Base64 列表
        furniture_nodes: 家具节点列表

    Returns:
        审计结果列表
    """
    if len(crop_images_b64) != len(furniture_nodes):
        raise ValueError("crop_images_b64 和 furniture_nodes 长度必须一致")

    if not crop_images_b64:
        return []

    # 使用线程池并发执行
    results: list[dict[str, Any]] = [{}] * len(crop_images_b64)

    def _worker(args: tuple[str, FurnitureNode]) -> tuple[int, dict[str, Any]]:
        idx, (img_b64, node) = args
        result = agent_2_audit_single(img_b64, node)
        return idx, result

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(crop_images_b64), 8)) as executor:
        futures = {
            executor.submit(_worker, (i, (img, node))): i
            for i, (img, node) in enumerate(zip(crop_images_b64, furniture_nodes))
        }

        for future in concurrent.futures.as_completed(futures):
            idx, result = future.result()
            results[idx] = result

    # 更新 furniture_list 中的 pass_2_audit 字段
    for node in furniture_nodes:
        for res in results:
            if res.get("furniture_id") == node["id"]:
                node["pass_2_audit"] = json.dumps(res)
                break

    return results


# ════════════════════════════════════════════════════════════════════════════════
# 异步版本 (待智谱 SDK 支持 async 后启用)
# ════════════════════════════════════════════════════════════════════════════════

async def agent_2_audit_single_async(
    crop_image_b64: str,
    furniture_node: FurnitureNode,
) -> dict[str, Any]:
    """Agent 2: 单件审计 (异步版本，待 SDK 支持后启用)。"""
    # 目前智谱 SDK 不支持 async，使用线程池包装
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, agent_2_audit_single, crop_image_b64, furniture_node)


async def agent_2_audit_batch_async(
    crop_images_b64: list[str],
    furniture_nodes: list[FurnitureNode],
) -> list[dict[str, Any]]:
    """Agent 2: 批量审计 (异步版本)。"""
    tasks = [
        agent_2_audit_single_async(img, node)
        for img, node in zip(crop_images_b64, furniture_nodes)
    ]
    return await asyncio.gather(*tasks)


# ════════════════════════════════════════════════════════════════════════════════
# 兼容性别名 (向后兼容)
# ════════════════════════════════════════════════════════════════════════════════

def analyze_room_image(
    image_path: str,
    calibration_data: dict | None = None,
) -> GraphState:
    """【兼容性别名】Agent 1: 从图像提取 BBox。

    此函数是 `agent_1_extract` 的别名，保持向后兼容。

    Args:
        image_path: 图片文件路径
        calibration_data: 校准数据 {"ref_object": str, "ref_size_mm": float}

    Returns:
        GraphState，包含 furniture_list 和 boundary
    """
    return agent_1_extract(image_path, calibration_data)


def analyze_room_images(
    image_paths: list[str],
    calibration_data: dict | None = None,
) -> GraphState:
    """【兼容性别名】Agent 1: 多图提取（取第一张）。

    此函数是 `agent_1_extract` 的别名，多图模式暂时取第一张。

    Args:
        image_paths: 图片文件路径列表
        calibration_data: 校准数据

    Returns:
        GraphState
    """
    if not image_paths:
        raise ValueError("image_paths 不能为空")
    return agent_1_extract(image_paths[0], calibration_data)
