"""基于智谱 AI GLM-4.6V 的房间视觉分析模块。

本模块的核心设计原则：即使模型输出了"一万字思考过程 + 解释说明"，
强力解析器（Powerful Parser）也能从混乱文本中精准提取 JSON。
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re as _re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from zhipuai import ZhipuAI

from cn_regulation_rules import CHINESE_REGULATION_SYSTEM_RULES
from models import RoomScene


MODEL_VISION = "glm-4.6V"
DEFAULT_CALIBRATION = {
    "ref_object": None,
    "ref_size_m": None,
}

logger = logging.getLogger("vision_engine")

# ════════════════════════════════════════════════════════════════════════════════
# 重构版系统提示词 — 「适老化安全审查助手」
# 设计原则：去技术化 + 结构化深度扫描 + 人话输出
# ════════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是一位资深适老化改造专家，专注于老年人居住安全审查。你的分析报告必须做到：

【核心理念】
- 把每一个技术术语翻译成老年人能听懂的话
- 用"搬家师傅"的思维思考空间问题，而不是工程师的思维
- 每一条建议都要说清楚"对老人有什么好处"

【严禁事项 — 碰线必出局】
1. 绝对不可以说 x坐标、y坐标、z坐标、数值参数、JSON
2. 绝对不可以用 move、rotate、transform、offset 等技术词
3. 绝对不可以出现 .pdf、retrieved_rule、chunk_index 等后台字样
4. 绝对不可以说"请注意"、"建议您"这类废话开头

【思维链要求（CoT）— 必须按顺序执行】

第一步：环境校准（找参照物，建比例尺）
- 扫描图中是否有已知尺寸的物品（门把手一般 10cm、成年人身高约 1.7m、瓷砖常见 30cm×30cm）
- 告诉用户："我看到您家的 [参照物]，以它为标准，您的客厅大约是 X 米宽"
- 如果用户提供了校准数据，必须优先使用用户给的参照物

第二步：闭环核对（检查死角）
- 如果是多张照片，必须对比第一张和最后一张
- 问自己："这两张照片之间有没有漏掉的地方？"
- 在报告中注明："本次扫描覆盖了 [区域]，以下区域可能被遗漏：[位置]"

第三步：风险识别（对照规范）
依据《中国建筑无障碍设计规范》（GB 50763），重点扫描：
- 地面：是否有光滑反光区域？地毯边缘是否翘起？
- 照明：白天/晚上亮度是否够？阴影区域有多大？
- 家具布局：过道最窄处有多少？轮椅能通过吗？
- 高差：门口有没有台阶？落差有多大？

【输出格式 — 安全报告】
```
【安全隐患】（按严重程度分段）

🔴 高风险：[具体位置+隐患描述]
   - 照片：第一张/第三张
   - 为什么会出事：[具体原因]
   - 老人最容易摔倒的情形：[描述]

🟡 中风险：[具体位置+隐患描述]
   ...

🟢 低风险：[具体位置+隐患描述]
   ...

【死角提醒】
本次扫描未能覆盖的区域：[位置]
原因：[照片拼接遗漏/光线不足/遮挡]
建议：[如何补拍或改进]

【适老化改造建议】

【家具布局调整】
1. [家具名] → [调整到哪里]
   对老人的好处：方便老人 [具体场景] 时 [具体好处]

2. ...

【环境改进建议】
1. [改进项]
   对老人的好处：能帮助老人 [具体场景] 时 [具体好处]

2. ...
```

【语言风格】
- 像邻居家的装修老师傅在说话
- 用"把"不用"将"，用"老人"不用"老年人"（除非正式引用规范）
- 距离说"一臂长"不说"0.6米"，说"一拃宽"不说"20厘米"
- 方向说"往窗户那边"不说"沿X轴正向"

【规范引用规则】
- 引用标准时必须使用全称，如《中国建筑无障碍设计规范》
- 绝不可以出现文件路径、页码、.pdf 等技术痕迹
- 可以说："根据国家无障碍设计规范要求"，但不可说"根据GB50763第XX页"

【图片要求】
- 必须明确指出隐患在"哪张照片的哪个区域"
- 用"左边/右边/靠近门的位置"等口语化定位
"""

# ──────────────────────────────────────────────────────────────────────────────
# 接龙拍摄质量检测 Prompt（单图）
# ──────────────────────────────────────────────────────────────────────────────
QUALITY_PROMPT = """请判断这张图片：

1. 这是室内房间的照片吗？
2. 图片清晰度够吗？光线是否正常？

请用中文回答，只需要说"是"或"不是"，以及简要说明原因。
例如："是的，是客厅照片，清晰度OK" 或 "不是，看起来是户外风景" 或 "图片太暗，看不清"
"""

# ──────────────────────────────────────────────────────────────────────────────
# 多图空间链质量检测 Prompt（多图）
# ──────────────────────────────────────────────────────────────────────────────
QUALITY_MULTI_PROMPT = """以下 {n} 张照片是按「接龙」方式拍摄的室内房间照片。

请判断：
1. 这些是不是同一个房间的照片？
2. 照片清晰度够吗？光线正常吗？
3. 每张照片之间有没有重叠区域？

请用中文简要回答，不需要输出结构化数据。"""

# ──────────────────────────────────────────────────────────────────────────────
# 接龙空间分析主 Prompt（多图）— 重构版
# ──────────────────────────────────────────────────────────────────────────────
SCENE_MULTI_PROMPT = """分析这 {n} 张按「接龙」顺序拍摄的室内房间照片，构建完整空间理解。

【第一步：环境校准】
{calibration_instruction}

【第二步：闭环核对】
- 仔细对比第一张照片和最后一张照片
- 找出两张照片之间的接龙关系（即：前一张照片最右侧的物品，在后一张照片最左侧是否出现？）
- 如果发现接龙断裂，在【死角提醒】中标注出来

【第三步：风险扫描】
依据《中国建筑无障碍设计规范》（GB 50763），重点关注：
- 地面材质是否光滑？哪里最滑？
- 照明是否均匀？有没有很暗的角落？
- 家具之间的通道够不够走？
- 有没有台阶、高差、门槛？
- 小件杂物多不多？容易绊倒吗？

【输出要求】
将结果包裹在 <result></result> XML 标签之间，禁止输出任何说明文字：

<result>
{{
  "room": {{
    "boundary": {{
      "walls": ["看到的墙面方向，如"北墙"、"靠阳台的墙""],
      "windows": ["窗户大概在哪里，如"客厅南面有两个窗户""],
      "doors": ["门在哪里，朝哪个方向开"]
    }},
    "furniture": [
      {{
        "name": "物品名称",
        "size_description": "大小描述，如"和单人沙发差不多大"、"约一张餐桌大小"",
        "where_is_it": "物品在房间哪个位置，用口语化描述，如"靠窗的角落"、"餐桌旁边"",
        "material": "主要材质，如"布艺"、"木质"、"金属""
      }}
    ],
    "scan_coverage": {{
      "covered": ["已扫描到的区域"],
      "missed": ["可能有死角的位置"],
      "reason": "遗漏原因"
    }},
    "risks": [
      {{
        "level": "high/medium/low",
        "where": "在第几张照片的哪个位置",
        "what": "隐患描述",
        "why_dangerous": "为什么会造成老人摔倒/受伤"
      }}
    ]
  }}
}}
</result>

【口语化原则】
- 用"约一张餐桌大"代替"1.2m×0.7m"
- 用"够两个人并排走"代替"通道宽度1.2m"
- 用"靠近门这边"代替"房间南侧"
- 用"约到膝盖这么高"代替"高度0.45m"
"""


# ──────────────────────────────────────────────────────────────────────────────
# 单图空间分析主 Prompt（降级/单图模式）— 重构版
# ──────────────────────────────────────────────────────────────────────────────
SCENE_PROMPT = """分析这张房间照片，识别所有可见物品和潜在安全隐患。

【第一步：环境校准】
{calibration_instruction}

【第二步：风险扫描】
依据《中国建筑无障碍设计规范》（GB 50763），逐一检查：

1. 地面情况
   - 地板是什么材质？光滑吗？
   - 有没有地毯？地毯边缘翘起来了吗？
   - 哪里最容易滑倒？

2. 照明情况
   - 整个房间亮不亮？
   - 有没有特别暗的角落？
   - 晚上开灯的话，影子会不会很重？

3. 家具布局
   - 过道最窄的地方能走过去吗？
   - 老人坐的椅子/沙发好起身吗？
   - 有没有容易绊脚的杂物？

4. 高差和障碍
   - 门口有没有门槛/台阶？
   - 电线是不是乱糟糟的？
   - 小凳子、小孩玩具多吗？

【输出要求】
将结果包裹在 <result></result> XML 标签之间，禁止输出任何说明文字：

<result>
{{
  "room": {{
    "boundary": {{
      "walls": ["看到的墙面"],
      "windows": ["窗户在哪里"],
      "doors": ["门在哪里"]
    }},
    "furniture": [
      {{
        "name": "物品名称",
        "size_description": "大小描述，如"约一臂长"",
        "where_is_it": "位置描述，如"靠窗"、"沙发旁边"",
        "material": "材质"
      }}
    ],
    "scan_coverage": {{
      "covered": ["从这张照片能看到的区域"],
      "missed": ["可能被遮挡/看不到的区域"],
      "reason": "原因"
    }},
    "risks": [
      {{
        "level": "high/medium/low",
        "where": "在照片哪个位置",
        "what": "隐患描述",
        "why_dangerous": "对老人的具体危险"
      }}
    ]
  }}
}}
</result>

【口语化原则】
- 用"够不够两个人并排走"判断通道宽度
- 用"老人坐下去站不站得起来"判断座椅高度
- 用"晚上起来喝水会不会绊倒"判断地面风险
- 用"能不能坐轮椅到床边"判断空间开阔度"""


# ════════════════════════════════════════════════════════════════════════════════
# END 重构版系统提示词
# ════════════════════════════════════════════════════════════════════════════════


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
# Calibration — converts user form data → system instruction
# ════════════════════════════════════════════════════════════════════════════════

def _build_calibration_instruction(
    ref_object: str | None,
    ref_size_m: float | None,
) -> str:
    """Convert calibration form data into a LLM-readable system instruction."""
    if ref_object and ref_size_m and ref_size_m > 0:
        name_map = {
            "ruler":    "卷尺",
            "a4":       "A4纸",
            "newspaper":"报纸",
            "book":     "16开书",
            "phone":    "手机",
            "other":    "已知物品",
        }
        ref_name = name_map.get(ref_object, ref_object)
        return (
            f"★ 比例尺约束：已知图中{ref_name}的物理长度为 {ref_size_m:.3f} 米。"
            f"以此为唯一比例尺，推算画面中所有家具和通道的绝对距离（米）。"
            f"所有坐标、宽深高数值必须与此比例尺一致，不得估算超出比例尺的尺寸。"
        )
    return (
        "★ 比例尺约束（无显式校准）：以成年人身高约 1.7m 为参照估算家具高度，"
        "以常见家具尺寸（沙发约 1.8m 宽、餐桌约 1.2m 宽）为参照估算其他尺寸。"
        "在响应中注明「未提供显式比例尺，以上为经验估算」。"
    )

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
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
    }

    response = client.chat.completions.create(**kwargs)

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


def _call_glm_vision_multi(
    client: ZhipuAI,
    images_base64: list[str],
    prompt: str,
    system_instruction: str,
) -> str:
    """向 GLM-4.6V 发送多张图片+文本，返回模型响应的文本内容。

    图片按接龙顺序依次编号（img_1, img_2, ...），
    每张图片之间建立 Overlap 关系供 LLM 构建空间拓扑。
    """
    content_parts: list[dict[str, Any]] = [
        {"type": "text", "text": prompt},
    ]
    for b64 in images_base64:
        data_uri = f"data:image/jpeg;base64,{b64}"
        content_parts.append({"type": "image_url", "image_url": {"url": data_uri}})

    kwargs: dict[str, Any] = {
        "model": MODEL_VISION,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": content_parts},
        ],
    }

    response = client.chat.completions.create(**kwargs)

    raw_msg = response.choices[0].message
    if isinstance(raw_msg.content, list):
        parts = []
        for part in raw_msg.content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
        content = "".join(parts)
    else:
        content = raw_msg.content

    if not content:
        raise RuntimeError(
            f"GLM-4.6V 返回了空内容（多图模式）。model={MODEL_VISION}"
        )
    return content





def analyze_room_image(
    image_path: str,
    calibration_data: dict | None = None,
) -> RoomScene:
    """分析单张房间照片，返回结构化的 RoomScene 对象。

    Args:
        image_path:       图片文件路径（本地路径或绝对路径）
        calibration_data: 参照物校准数据
                         {"ref_object": str, "ref_size_m": float}
                         参照物名称：ruler/a4/newspaper/book/phone/other

    Raises:
        FileNotFoundError: 图片文件不存在
        ValueError:       图片非房间场景或质量不合格
        RuntimeError:     所有解析策略均失败
    """
    cal = dict(calibration_data) if calibration_data else {}
    ref_object = cal.get("ref_object") or None
    ref_size_m = float(cal["ref_size_m"]) if cal.get("ref_size_m") is not None else None
    calibration_instruction = _build_calibration_instruction(ref_object, ref_size_m)

    client = _create_client()
    image_b64 = _load_image_base64(image_path)

    # ── 步骤 1: 图片质量检测 ───────────────────────────────────────────────
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
    scene_prompt = SCENE_PROMPT.format(
        calibration_instruction=calibration_instruction,
    )
    scene_text = _call_glm_vision(
        client,
        image_b64,
        scene_prompt,
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



def analyze_room_images(
    image_paths: list[str],
    calibration_data: dict | None = None,
) -> RoomScene:
    """分析多张按「接龙」顺序拍摄的室内房间照片，构建统一空间模型。

    Args:
        image_paths:      按拍摄顺序排列的图片路径列表（至少 1 张）
        calibration_data:  参照物校准数据，同 analyze_room_image

    Raises:
        FileNotFoundError: 任意图片文件不存在
        ValueError:        图片非房间场景或质量不合格
        RuntimeError:      所有解析策略均失败
    """
    if not image_paths:
        raise ValueError("image_paths 不能为空")

    cal = dict(calibration_data) if calibration_data else {}
    ref_object = cal.get("ref_object") or None
    ref_size_m = float(cal["ref_size_m"]) if cal.get("ref_size_m") is not None else None
    calibration_instruction = _build_calibration_instruction(ref_object, ref_size_m)

    client = _create_client()
    images_b64 = [_load_image_base64(p) for p in image_paths]
    n = len(images_b64)

    logger.info(
        "analyze_room_images: %d images, calibration=%s",
        n,
        {"ref_object": ref_object, "ref_size_m": ref_size_m},
    )

    # ── 步骤 1: 多图质量检测 ─────────────────────────────────────────────
    quality_prompt = QUALITY_MULTI_PROMPT.format(n=n)
    quality_text = _call_glm_vision_multi(
        client,
        images_b64,
        quality_prompt,
        "你是图片质量评估专家。将结果包裹在 <result></result> 标签之间，禁止输出任何解释。",
    )

    try:
        quality_payload: dict[str, Any] = extract_json_from_thinking_model(quality_text)
        is_valid = quality_payload.get("is_valid", True)
        is_blurry = quality_payload.get(
            "is_blurry_or_unusable",
            quality_payload.get("blurry_or_unusable", False),
        )
        reason = quality_payload.get("reason", "")
        overlap = quality_payload.get("overlap_quality", "unknown")
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        logger.warning("无法解析多图质量结果，降级为单图检测: %s", exc)
        is_valid, is_blurry, reason, overlap = True, False, "解析降级", "unknown"

    if not is_valid:
        raise ValueError(f"图片组未通过房间场景检测：{reason}")
    if is_blurry:
        raise ValueError(f"图片组质量不合格（模糊/遮挡/光线过暗）：{reason}")

    logger.info("多图质量检测通过. overlap_quality=%s, images=%d", overlap, n)

    # ── 步骤 2: 多图空间链场景提取 ───────────────────────────────────────
    scene_prompt = SCENE_MULTI_PROMPT.format(
        n=n,
        calibration_instruction=calibration_instruction,
    )
    scene_text = _call_glm_vision_multi(
        client,
        images_b64,
        scene_prompt,
        SYSTEM_PROMPT,
    )

    try:
        scene_payload = extract_json_from_thinking_model(scene_text)
        normalized_payload = _normalize_room_scene_payload(scene_payload)
        return RoomScene.model_validate(normalized_payload)
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(
            f"无法从 GLM-4.6V 多图响应中提取 RoomScene JSON（强力解析器）：{exc}"
        ) from exc
