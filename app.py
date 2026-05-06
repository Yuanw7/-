"""
建筑合规审查 Agent — Streamlit 前端
专业适老化房间安全分析界面

启动方式:
  后端: python main.py          (http://0.0.0.0:8000)
  前端: streamlit run app.py     (http://localhost:8501)
"""

from __future__ import annotations

from pathlib import Path

import requests
import streamlit as st
from streamlit_extras.row import row as st_row
from streamlit_extras.stylable_container import stylable_container as st_scontainer

# ── Configuration ──────────────────────────────────────────────────────────────

# Default API base URL. Override via sidebar if using ngrok.
_API_OPTIONS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    # Add your ngrok URL here, e.g. "https://xxxx-00-12-345-678-90.ngrok-free.app"
]

TIMEOUT_SEC = 120
MAX_FILE_SIZE_MB = 10
SUPPORTED_FORMATS = {"jpg", "jpeg", "png", "webp"}

_api_base = {"value": "http://localhost:8000"}  # mutable container to allow sidebar to set it

# ── Page Setup ─────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="建筑合规审查 Agent",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS — Professional Architecture Aesthetic ──────────────────────────

st.html("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&family=JetBrains+Mono:wght@400;500&display=swap');

  :root {
    --primary:       #1A3A5C;
    --accent:        #2E7D6B;
    --accent-light:  #E8F5F1;
    --warn:          #C0392B;
    --bg:            #F7F9FB;
    --card-bg:       #FFFFFF;
    --border:        #D0D9E4;
    --text:          #1E2A3A;
    --text-muted:    #6B7A8C;
    --mono:          'JetBrains Mono', monospace;
    --body:          'Noto Sans SC', sans-serif;
  }

  html, body, .stApp { font-family: var(--body); background: var(--bg); color: var(--text); }

  /* Header */
  .main-header {
    background: linear-gradient(135deg, #1A3A5C 0%, #2E7D6B 100%);
    padding: 1.8rem 2rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    color: white;
  }
  .main-header h1 { font-size: 1.6rem; font-weight: 700; margin: 0; letter-spacing: 0.02em; }
  .main-header p  { font-size: 0.88rem; opacity: 0.82; margin: 0.3rem 0 0; font-weight: 300; }

  /* Cards */
  .result-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 4px rgba(26,58,92,0.06);
  }

  /* Status badges */
  .badge-approved  { background: #E8F5F1; color: #1B6B52; border: 1px solid #A7D7C5; padding: 4px 14px; border-radius: 20px; font-size: 0.82rem; font-weight: 600; }
  .badge-rejected { background: #FDECEA; color: #B03A2E; border: 1px solid #E8A09A; padding: 4px 14px; border-radius: 20px; font-size: 0.82rem; font-weight: 600; }
  .badge-neutral  { background: #EBF2FA; color: #1A3A5C; border: 1px solid #A8C1DA; padding: 4px 14px; border-radius: 20px; font-size: 0.82rem; font-weight: 600; }

  /* Blueprint table */
  .bp-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  .bp-table th { background: var(--primary); color: white; padding: 8px 12px; text-align: left; }
  .bp-table td { padding: 7px 12px; border-bottom: 1px solid #E8EEF5; }
  .bp-table tr:hover td { background: #F0F6FB; }

  /* Code blocks */
  .stCodeBlock { border-radius: 8px; border: 1px solid var(--border); }

  /* Section headers */
  .section-title {
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-muted);
    border-bottom: 2px solid var(--accent);
    padding-bottom: 4px;
    margin-bottom: 0.8rem;
  }

  /* Spinner text */
  .spinner-msg { font-size: 0.9rem; color: var(--text-muted); }

  /* Upload highlight */
  [data-testid="stFileUploaderDropzone"] { border: 2px dashed #2E7D6B !important; border-radius: 12px !important; }
  [data-testid="stFileUploaderDropzone"]:hover { border-color: #1A3A5C !important; }

  /* Sidebar */
  section[data-testid="stSidebar"] { background: #EEF3F8; border-right: 1px solid var(--border); }

  /* Markdown h2 */
  .stMarkdown h2 { font-size: 1.1rem; color: var(--primary); margin-top: 0.5rem; }
  .stMarkdown h3 { font-size: 0.95rem; color: var(--accent); }
</style>
""")

# ── Helpers ────────────────────────────────────────────────────────────────────

def render_status_badge(status: str) -> str:
    """Return HTML badge string for a given status."""
    cls = {
        "APPROVED": "badge-approved",
        "REJECTED": "badge-rejected",
    }.get(status, "badge-neutral")
    return f'<span class="{cls}">{status}</span>'


def render_safety_score_bar(score: float) -> tuple[str, str]:
    """Return (color, label) for a safety score 0–100."""
    if score >= 80:
        return "#2E7D6B", f"安全 ({score:.0f}/100)"
    if score >= 60:
        return "#F39C12", f"待改进 ({score:.0f}/100)"
    return "#C0392B", f"危险 ({score:.0f}/100)"


def parse_safety_score(text: str) -> float:
    """Extract the numeric safety score from markdown text."""
    import re

    m = re.search(r"Safety Score[:\s]*\*\*?(\d+\.?\d*)\*\*/100\*\*?", text)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+\.?\d*)/100", text)
    if m:
        return float(m.group(1))
    return 0.0


def parse_blueprint_table(md_text: str) -> list[dict]:
    """Extract furniture rows from the 2D blueprint markdown."""
    import re

    rows = []
    lines = md_text.splitlines()
    for line in lines:
        if line.startswith("|") and "Furniture" not in line and "---" not in line:
            parts = [p.strip() for p in line.strip().strip("|").split("|")]
            if len(parts) >= 6:
                rows.append({
                    "Furniture": parts[0],
                    "X": parts[1],
                    "Y": parts[2],
                    "Rotation(°)": parts[3],
                    "W(m)": parts[4],
                    "D(m)": parts[5],
                    "H(m)": parts[6] if len(parts) > 6 else "—",
                    "Material": parts[7] if len(parts) > 7 else "—",
                })
    return rows


# ── Header ────────────────────────────────────────────────────────────────────

st.html('<div class="main-header"><h1>🏗️ 建筑合规审查 Agent</h1><p>基于 GB 50016 · GB 50222 · GB 50352 · GB 50763 标准的适老化房间安全分析系统</p></div>')

# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### ⚙️ 配置")
    st.caption("确保后端已启动:")
    st.code("python main.py", language="bash")

    # ── API Endpoint selector ───────────────────────────────────────────────────
    st.markdown("#### 🌐 API 地址")
    custom_url = st.text_input(
        "输入 ngrok 或自定义 URL",
        placeholder="https://your-ngrok.ngrok-free.app",
        help="如果使用 ngrok 暴露后端，请在此填入 ngrok 提供的完整 URL。",
    )
    if custom_url.strip():
        _api_base["value"] = custom_url.strip().rstrip("/")
    else:
        selected = st.selectbox("选择本地后端", _API_OPTIONS, index=0)
        _api_base["value"] = selected

    st.markdown("---")
    st.markdown("#### 📋 GB 标准覆盖")
    st.markdown("""
    - **GB 50016** 建筑设计防火规范
    - **GB 50222** 内部装修防火规范
    - **GB 50352** 民用建筑设计统一标准
    - **GB 50763** 无障碍设计规范
    """)
    st.markdown("---")
    st.markdown("#### ℹ️ 使用说明")
    st.markdown("""
    1. 上传房间照片（JPG/PNG）
    2. 点击 **开始分析**
    3. 查看结构化合规报告
    4. 导出 Blender 脚本或 2D 蓝图
    """)
    st.markdown("---")
    api_status = st.button("🔄 检测后端连接", use_container_width=True)

    if api_status:
        try:
            r = requests.get(f"{_api_base['value']}/health", timeout=5)
            if r.status_code == 200:
                st.success(f"✅ 后端在线 ({r.json().get('version','?')})")
            else:
                st.error(f"⚠️ 后端异常: {r.status_code}")
        except Exception as e:
            st.error(f"❌ 无法连接后端:\n`{e}`")

# ── Main Layout ───────────────────────────────────────────────────────────────

col_upload, col_actions = st.columns([1, 0.35])

with col_upload:
    st.markdown('<p class="section-title">📤 上传房间照片</p>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader(
        label="支持 JPG / PNG / WebP，最大 10MB",
        type=["jpg", "jpeg", "png", "webp"],
        label_visibility="collapsed",
        accept_multiple_files=False,
    )

with col_actions:
    st.markdown("&nbsp;")  # vertical spacing
    run_analysis = st.button(
        "🔍 开始分析",
        type="primary",
        use_container_width=True,
        disabled=(uploaded_file is None),
    )

# ── Results State ─────────────────────────────────────────────────────────────

if "analysis_result" in st.session_state:
    del st.session_state["analysis_result"]
if "thinking_done" in st.session_state:
    del st.session_state["thinking_done"]

# ── Run Analysis ───────────────────────────────────────────────────────────────

if run_analysis and uploaded_file:
    file_ext = Path(uploaded_file.name).suffix.lower().lstrip(".")
    if file_ext not in SUPPORTED_FORMATS:
        st.error(f"不支持的文件格式: .{file_ext}")
        st.stop()

    file_size_mb = uploaded_file.size / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        st.error(f"文件过大 ({file_size_mb:.1f}MB)，请控制在 {MAX_FILE_MB}MB 以内。")
        st.stop()

    # Prepare progress placeholders
    status_container = st.empty()
    progress_bar = st.progress(0, text="")
    thinking_placeholder = st.empty()

    def update_status(step: str, pct: int):
        status_container.markdown(f"**📍 {step}**")
        progress_bar.progress(pct, text=step)

    # ── Step 1: Upload ────────────────────────────────────────────────────────
    update_status("⏫ 正在上传图片并提交分析请求...", 10)
    thinking_placeholder.info("🔄 正在连接后端 API...")

    try:
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
        update_status("🤖 Gemini Vision 正在分析房间场景...", 25)
        thinking_placeholder.info(
            "🧠 AI 正在识别家具布局、测量尺寸、检测潜在安全隐患..."
        )

        response = requests.post(
            f"{_api_base['value']}/analyze-room",
            files=files,
            timeout=TIMEOUT_SEC,
        )

        update_status("🔍 Agent 安全审查中 (proposer-critic 循环)...", 55)
        thinking_placeholder.info(
            "🏛️ 正在对照 GB 标准进行合规审查，检索知识库..."
        )

        if response.status_code == 413:
            thinking_placeholder.error("❌ 文件超过 10MB 限制。")
            st.stop()

        if response.status_code != 200:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            thinking_placeholder.error(f"❌ 后端错误 ({response.status_code}): {detail}")
            st.stop()

        update_status("📊 生成结构化输出...", 80)
        thinking_placeholder.info(
            "📝 正在生成 2D 蓝图、安全报告、适老化建议..."
        )

        result = response.json()
        update_status("✅ 分析完成", 100)
        thinking_placeholder.empty()
        progress_bar.empty()
        status_container.empty()

        st.session_state["analysis_result"] = result
        st.session_state["thinking_done"] = True
        st.rerun()

    except requests.exceptions.Timeout:
        thinking_placeholder.error(
            f"⏱️ 请求超时（>{TIMEOUT_SEC}s）。图片可能过于复杂，请重试或使用更清晰的图片。"
        )
    except requests.exceptions.ConnectionError:
        thinking_placeholder.error(
            "❌ 无法连接到后端。请确认 `python main.py` 已启动于 http://localhost:8000"
        )
    except Exception as e:
        thinking_placeholder.error(f"❌ 发生错误: {e}")

# ── Display Results ────────────────────────────────────────────────────────────

if "analysis_result" in st.session_state:
    result = st.session_state["analysis_result"]

    status = result.get("status", "UNKNOWN")
    safety_md = result.get("safety_report_markdown", "")
    safety_score = parse_safety_score(safety_md)

    # ── Summary Cards ────────────────────────────────────────────────────────
    st.markdown("---")
    row1 = st_row([1, 1, 1], gap="small")

    with row1[0]:
        badge_html = render_status_badge(status)
        with st_scontainer(key="status_card"):
            st.markdown('<p class="section-title">审核结果</p>', unsafe_allow_html=True)
            st.html(badge_html)

    with row1[1]:
        score_color, score_label = render_safety_score_bar(safety_score)
        with st_scontainer(key="score_card"):
            st.markdown('<p class="section-title">安全评分</p>', unsafe_allow_html=True)
            st.markdown(
                f"<span style='font-size:2rem;font-weight:700;color:{score_color}'>"
                f"{safety_score:.0f}</span>"
                f"<span style='font-size:0.9rem;color:var(--text-muted)'>/100</span>",
                unsafe_allow_html=True,
            )
            st.caption(score_label)

    furniture_count = len(result.get("room_scene", {}).get("furniture", []))
    with row1[2]:
        with st_scontainer(key="count_card"):
            st.markdown('<p class="section-title">检测家具</p>', unsafe_allow_html=True)
            st.markdown(
                f"<span style='font-size:2rem;font-weight:700;color:var(--primary)'>"
                f"{furniture_count}</span><span style='font-size:0.9rem;color:var(--text-muted)'> 件</span>",
                unsafe_allow_html=True,
            )

    # ── Tab Layout ───────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 安全报告",
        "🗺️ 2D 蓝图",
        "🔄 变更清单",
        "🪑 适老化建议",
        "🧱 Blender 脚本",
    ])

    with tab1:
        st.markdown("### 📋 安全报告")
        st.markdown(
            safety_md or "*安全报告生成失败*",
            unsafe_allow_html=False,
        )

        st.markdown("---")
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("### 🔄 变更追踪")
            trace = result.get("failure_trace", [])
            if trace:
                for item in trace:
                    st.warning(f"⚠️ {item}")
            else:
                st.success("✅ 无违规追踪记录")

        with col_right:
            st.markdown("### 👤 用户友好建议")
            st.info(result.get("user_friendly_suggestions_text", "") or "*暂无建议*")

    with tab2:
        st.markdown("### 🗺️ 2D 房间蓝图 (俯视图)")
        blueprint_md = result.get("blueprint_2d_markdown", "")
        st.markdown(blueprint_md, unsafe_allow_html=False)

        furniture_rows = parse_blueprint_table(blueprint_md)
        if furniture_rows:
            st.markdown("#### 📐 家具坐标表")
            st.dataframe(
                furniture_rows,
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("---")
        with st.expander("📄 查看完整 Blueprint Markdown 源码"):
            st.code(blueprint_md or "", language="markdown")

    with tab3:
        st.markdown("### 🔄 结构化变更公式 (Strict Change Formula)")

        strict_formula = result.get("strict_change_formula", {})
        if strict_formula:
            col_goal, col_floor = st.columns(2)
            with col_goal:
                st.metric("设计目标", strict_formula.get("program_goal", "—"))
            with col_floor:
                floor_suggestion = (
                    strict_formula.get("floor_texture", {}).get("suggestion", "—")
                )
                st.metric("地面材质建议", floor_suggestion[:40] + "..." if len(floor_suggestion) > 40 else floor_suggestion)

            st.markdown("#### 家具详情 (Furniture)")
            furniture_data = strict_formula.get("furniture", {})
            if furniture_data:
                furniture_rows_strict = [
                    {
                        "名称": name,
                        "材质": info.get("material", "—"),
                        "适老化": info.get("elder_friendliness", "—")[:30] + "...",
                        "X(m)": info.get("placement", {}).get("x", "—"),
                        "Y(m)": info.get("placement", {}).get("y", "—"),
                    }
                    for name, info in furniture_data.items()
                ]
                st.dataframe(furniture_rows_strict, use_container_width=True, hide_index=True)

            st.markdown("#### 必要变更 (Changes Required)")
            changes = strict_formula.get("changes_required", [])
            if changes:
                for i, change in enumerate(changes, 1):
                    with st.container():
                        st.markdown(f"**{i}. {change.get('target','—')}** — `{change.get('action','—')}`")
                        params = change.get("what_to_change", {})
                        if isinstance(params, dict):
                            for k, v in params.items():
                                st.write(f"&nbsp;&nbsp;&nbsp;`{k}`: `{v}`")
                        grounding = change.get("grounding", {})
                        if grounding and grounding.get("rule_id"):
                            st.caption(
                                f"📖 依据: {grounding.get('rule_id','?')} | "
                                f"来源: {grounding.get('source_file','?')} p.{grounding.get('page_number','?')}"
                            )
                        st.markdown("")
            else:
                st.success("✅ 当前布局无需强制变更")

            # RAG grounding
            rag_results = strict_formula.get("rag_strict_grounding", [])
            if rag_results:
                with st.expander(f"📚 RAG 知识库检索结果 ({len(rag_results)} 条)"):
                    for item in rag_results:
                        st.markdown(
                            f"**{item.get('rule_id','?')}** "
                            f"`{item.get('source_file','?')}` p.{item.get('page_number','?')}"
                            f" | score: `{item.get('score',0):.4f}`"
                        )
                        st.caption(f"_{item.get('snippet','')[:200]}_")
                        st.divider()
        else:
            st.warning("未获取到变更公式数据")

    with tab4:
        st.markdown("### 🪑 适老化详细建议")
        st.markdown(
            result.get("elder_redesign_suggestions_markdown", ""),
            unsafe_allow_html=False,
        )

    with tab5:
        st.markdown("### 🧱 Blender 3D 重建脚本")
        st.caption("在 Blender 中打开: Text Editor → New → Paste → Run Script")
        blender_code = result.get("blender_script", "")
        st.code(blender_code, language="python", line_numbers=True)

        if blender_code:
            st.download_button(
                "⬇️ 下载 Blender 脚本",
                data=blender_code,
                file_name="room_scene_generator.py",
                mime="text/x-python",
                use_container_width=True,
            )

    # ── Final Notes ─────────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("📄 查看完整 API 原始响应 (JSON)"):
        import json

        st.json(result, expanded=False)

    st.markdown(
        "<p style='text-align:center;color:var(--text-muted);font-size:0.75rem'>"
        "建筑合规审查 Agent · GB 50016/50222/50352/50763 · Powered by Gemini + LangGraph"
        "</p>",
        unsafe_allow_html=True,
    )
