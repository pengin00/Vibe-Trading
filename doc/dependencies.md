# 开源依赖与中间件

依赖声明主要位于 `pyproject.toml`、`agent/requirements.txt` 和 `frontend/package.json`。

## 后端核心依赖

| 依赖 | 用途 |
| --- | --- |
| `fastapi` | REST API 服务 |
| `uvicorn[standard]` | ASGI Server |
| `pydantic` | 请求/响应和领域模型校验 |
| `sse-starlette` | SSE 事件流 |
| `python-multipart` | 文件上传 |
| `langchain` / `langchain-core` / `langchain-openai` | LLM 抽象和 OpenAI 兼容调用 |
| `langgraph` / `langgraph-checkpoint` | Agent/图式编排能力 |
| `fastmcp` | MCP Server |
| `python-dotenv` | `.env` 配置加载 |
| `httpx` / `requests` | HTTP 客户端 |
| `rich` | CLI/TUI 展示 |
| `prompt_toolkit` | 交互式命令行输入体验 |

## 数据分析和量化依赖

| 依赖 | 用途 |
| --- | --- |
| `pandas` | 表格、行情、因子、回测数据结构 |
| `numpy` | 数值计算 |
| `scipy` | 统计和优化计算 |
| `duckdb` | 本地 Parquet/缓存读取写入 |
| `scikit-learn` | ML 策略和分析 |
| `joblib` | 并行/缓存辅助 |
| `matplotlib` | 报告图表 |

## 行情和金融数据依赖

| 依赖 | 用途 |
| --- | --- |
| `yfinance` | 美股、港股等免费行情 |
| `akshare` | A 股、港股、美股、期货、宏观等数据 |
| `tushare` | A 股和财务数据，可选 token |
| `ccxt` | 加密交易所行情 |
| `baostock` | 可选 A 股数据源，安装 extra `ashare` |
| `mootdx` | 通达信 TCP A 股行情，代码中有 loader，需环境具备依赖 |
| `futu` 相关 SDK | Futu OpenD 数据和交易连接，由 connector/loader 使用 |

## 文件和报告依赖

| 依赖 | 用途 |
| --- | --- |
| `openpyxl` | Excel 读取 |
| `python-docx` | Word 读取 |
| `python-pptx` | PowerPoint 读取 |
| `pypdfium2` | PDF 渲染/读取 |
| `Pillow` | 图片读取/OCR 辅助 |
| `jinja2` | HTML 报告模板 |
| `weasyprint` | HTML/PDF 报告渲染 |

## 前端依赖

| 依赖 | 用途 |
| --- | --- |
| `react` / `react-dom` | Web UI 框架 |
| `vite` | 前端构建和开发服务器 |
| `typescript` | 类型系统 |
| `react-router-dom` | 前端路由 |
| `zustand` | 状态管理 |
| `echarts` | 图表和热力图 |
| `lucide-react` | 图标 |
| `react-markdown` / `remark-gfm` | Markdown 渲染 |
| `highlight.js` / `rehype-highlight` | 代码高亮 |
| `sonner` | Toast 提示 |
| `tailwindcss` / `tailwind-merge` | 样式工具 |
| `vitest` / Testing Library | 前端测试 |

## Docker 组件

- `Dockerfile` 使用多阶段构建：
  - `node:20-slim` 构建前端。
  - `python:3.11-slim` 运行后端和静态前端。
- `docker-compose.yml` 默认启动后端服务，并可通过 profile 启动前端开发服务。
- 默认端口：
  - 后端/Web：`127.0.0.1:8899`
  - 前端 dev profile：`5899`

## 可选 extra

`pyproject.toml` 中定义了几个 optional dependencies：

- `ibkr`：安装 `ib_async`，用于 IBKR。
- `deepseek`：安装 `langchain-deepseek`，使用 DeepSeek 原生 adapter。
- `ashare`：安装 `baostock`。
- `harmonic`：安装 `pyharmonics`。
- `dev`：安装测试工具。

