# 建筑合规审查 Agent

基于 GB 50016 · GB 50222 · GB 50352 · GB 50763 标准的适老化房间安全合规审查系统。

Powered by **智谱 AI GLM-4** (视觉理解) + **智谱 AI Embedding-2** (向量化) + **LangGraph** (proposer-critic 安全审查循环) + **ChromaDB** (RAG 知识库) + **Cloudflare Tunnel** (零配置内网穿透)。

---

## 项目架构

```
┌──────────────────────────────────────────────────────────────┐
│                  前端 — Glassmorphism 静态页面                 │
│               index.html (浏览器直接访问)                      │
└──────────────────────────────┬───────────────────────────────┘
                               │ fetch('/analyze-room')
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                    后端 (FastAPI)                            │
│                    main.py (port 8080)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐    │
│  │vision_engine│→ │agent_logic  │→ │output_engine     │    │
│  │ (GLM-4)    │  │(LangGraph)  │  │(7种输出格式)    │    │
│  └─────────────┘  └──────┬──────┘  └──────────────────┘    │
│                            │                                  │
│                            ▼                                  │
│                   ┌────────────────┐                         │
│                   │knowledge_base  │                         │
│                   │(ChromaDB RAG) │                         │
│                   └────────────────┘                         │
└──────────────────────────────┬───────────────────────────────┘
                               │ cloudflared tunnel
                               ▼
                    ┌──────────────────────┐
                    │  Cloudflare 全球网络  │
                    │ *.trycloudflare.com  │
                    └──────────────────────┘
                               │
                               ▼
                    🌐 任意设备 / 任意网络访问
```

---

## 快速启动

### 第一步：安装依赖

```bash
pip install -r requirements.txt
```

### 第二步：配置智谱 AI Key

```bash
cp .env.example .env
# 编辑 .env，填入你的智谱 AI API Key
```

> 获取智谱 AI API Key: https://open.bigmodel.cn/usercenter/apikeys

### 第三步：启动后端

```bash
python main.py
# 后端运行于 http://localhost:8080
```

### 第四步：建立 Cloudflare Tunnel（零配置穿透）

**安装 cloudflared（首次需要）：**

```bash
# macOS
brew install cloudflared

# Linux
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
  -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
```

**启动隧道：**

```bash
python tunnel_manager.py
```

脚本会自动：
- 启动 `cloudflared tunnel --url http://localhost:8080`
- 实时解析输出中的公网链接
- 以醒目样式打印 `https://*.trycloudflare.com` 地址

```
══════════════════════════════════════════════════════════════
   🛡️  Cloudflare Tunnel Manager  |  Local: http://localhost:8080
══════════════════════════════════════════════════════════════

  ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★

     🌐  公网访问链接 (可分享给任何人):

        https://xxxx-xxxxxxxxxx.trycloudflare.com

  ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★

     按 Ctrl+C 停止隧道
```

### 第五步：开始使用

1. 打开脚本输出的 `*.trycloudflare.com` 链接
2. 上传房间照片 (JPG/PNG/WebP，最大 10MB)
3. 点击「开始分析」
4. 查看安全报告、2D 蓝图、适老化建议
5. 下载 Blender 3D 重建脚本

---

## 核心功能

| 功能 | 说明 |
|------|------|
| 📷 房间场景理解 | GLM-4 多模态视觉识别家具、尺寸、布局 |
| 🏛️ GB 合规审查 | LangGraph proposer-critic 循环 + RAG 知识库 |
| 📊 安全评分 | 多规则加权评分，精确到来源文件页码 |
| 🗺️ 2D 蓝图 | Markdown 表格 + 坐标系统一输出 |
| 🪑 适老化建议 | 针对老年人的空间安全建议 |
| 🧱 Blender 脚本 | 一键导出 3D 重建 Python 脚本 |
| 🌐 零配置穿透 | Cloudflare Tunnel，无需注册账号 |

---

## GB 标准覆盖

| 标准 | 编号 | 重点领域 |
|------|------|----------|
| 建筑设计防火规范 | GB 50016 | 防火间距、可燃材料、疏散通道 |
| 建筑内部装修设计防火规范 | GB 50222 | 装修材料防火等级 |
| 民用建筑设计统一标准 | GB 50352 | 空间组织、人体尺度 |
| 无障碍设计规范 | GB 50763 | 老年人/残障人士无障碍设施 |

---

## API 端点

### `GET /`

返回玻璃拟态前端页面（index.html）。

### `GET /health`

健康检查。

```json
{"status": "ok", "version": "1.0.0"}
```

### `POST /analyze-room`

上传房间图片进行合规审查。

**参数:** `file` (form-data, 图片文件)

**返回:**

```json
{
  "status": "APPROVED | REJECTED",
  "room_scene": { ... },
  "modification_proposals": [ ... ],
  "blueprint_2d_markdown": "...",
  "strict_change_formula": { ... },
  "elder_redesign_suggestions_markdown": "...",
  "safety_report_markdown": "...",
  "blender_script": "...",
  "user_friendly_suggestions_text": "...",
  "failure_trace": [ ... ],
  "reasoning_trace_file": "reasoning_trace.json"
}
```

---

## 项目文件说明

| 文件 | 说明 |
|------|------|
| `main.py` | FastAPI 后端入口，端口 8080 |
| `vision_engine.py` | 智谱 GLM-4 视觉图像理解 |
| `agent_logic.py` | LangGraph proposer-critic 安全审查循环 |
| `knowledge_base.py` | ChromaDB RAG 知识库 |
| `output_engine.py` | 7种输出格式生成器 |
| `models.py` | Pydantic 数据模型 |
| `cn_regulation_rules.py` | GB 标准规范注入 |
| `index.html` | 玻璃拟态前端（Tailwind CSS） |
| `tunnel_manager.py` | Cloudflare Tunnel 启动与 URL 提取脚本 |
| `requirements.txt` | Python 依赖清单 |
| `.env.example` | 环境变量模板 |
| `specs/` | GB 标准 PDF 文档 |
| `uploads/` | 临时上传文件目录 |

---

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `ZHIPUAI_API_KEY` | ✅ | 智谱 AI API Key |

---

## 首次运行说明

首次分析时，系统会从 `specs/` 文件夹中的 PDF 构建 ChromaDB 向量知识库，此过程可能需要 10-30 秒。后续分析将直接复用知识库，速度大幅提升。

---

## 注意事项

- Cloudflare Tunnel 链接每次重启 `tunnel_manager.py` 会变化
- 建议在 `.env` 中填入真实智谱 AI Key 后使用，免费额度足够个人测试
- 分析图片建议光线充足、房间清晰可见，效果最佳
