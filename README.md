# mineru-docparse-mcp

把 Word / PDF / PPT / Excel 转成 Markdown 的 MCP Server，基于 [MinerU DocParse API](https://github.com/opendatalab/MinerU)。

> 本项目只是协议封装层，本身不解析文档。使用前需要有一个可访问的 MinerU DocParse 服务，默认地址 `http://localhost:8000`。部署方式见 [MinerU 官方仓库](https://github.com/opendatalab/MinerU)。

## 安装

```bash
pip install mineru-docparse-mcp
```

## 配置到 Claude Code

保存路径是服务端配置，不是接口参数，所以 `MINERU_OUTPUT_DIR` 必须在这里设置好，否则调用解析工具时会报错：

```json
{
  "mcpServers": {
    "mineru": {
      "command": "mineru-docparse-mcp",
      "env": {
        "MINERU_API_URL": "http://localhost:8000",
        "MINERU_OUTPUT_DIR": "/Users/yourname/Documents/mineru-output"
      }
    }
  }
}
```

配好之后就能用了，Claude 会自动调用下面这些工具，解析结果统一存到 `MINERU_OUTPUT_DIR` 里。

## 工具

| 工具 | 用途 |
|---|---|
| `mineru_parse_document` | 解析文档，等待完成并直接把结果存到磁盘（默认用这个） |
| `mineru_submit_task` | 提交大文件到后台解析，立即返回 `task_id` |
| `mineru_get_task_status` | 查询后台任务进度 |
| `mineru_get_task_result` | 后台任务完成后取结果并存到磁盘 |
| `mineru_health_check` | 检查 MinerU 服务是否正常 |

普通文件直接说"帮我解析这个 PDF"就行，Claude 会用 `mineru_parse_document`。文件很大（上百页）时会自动改用后台任务的三个工具轮询。

**结果怎么存**：MinerU 返回什么格式就原样存成什么格式，本项目不解压、不解析内容——`response_format_zip=true`（默认）时存成 `.zip`，为 `false` 时存成 `.json`。文件名与源文件同名，若目录下已有同名文件会自动加时间戳，不覆盖。

## 接口参数

`mineru_parse_document` 和 `mineru_submit_task` 的参数完全一致，均对应 MinerU 官方 `/file_parse` 与 `/tasks` 接口的表单字段。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `file_path` | string | 必填 | 本地文档绝对路径（.docx/.pdf/.pptx/.xlsx 等） |
| `backend` | enum | `hybrid-engine` | 解析后端，见下方「backend 可选值」 |
| `lang_list` | string[] | `["ch"]` | OCR 语言列表，仅 `pipeline` 后端生效，见下方「lang_list 可选值」 |
| `effort` | `medium` \| `high` | `medium` | 仅 `hybrid` 后端生效。`medium` 更快但不含图表分析；`high` 精度更高、含图表分析、耗时更长 |
| `parse_method` | `auto` \| `txt` \| `ocr` | `auto` | 仅 `pipeline`/`hybrid` 后端生效的 PDF 解析方式：自动判断 / 纯文本提取 / OCR 识别 |
| `formula_enable` | bool | `true` | 是否解析公式（LaTeX 格式） |
| `table_enable` | bool | `true` | 是否解析表格 |
| `image_analysis` | bool | `true` | 是否分析图片/图表，仅 VLM/hybrid 后端生效 |
| `server_url` | string \| null | `null` | 仅 `*-http-client` 后端需要，OpenAI 兼容服务器地址，如 `http://127.0.0.1:30000` |
| `return_md` | bool | `true` | 响应中是否包含 Markdown 内容 |
| `return_middle_json` | bool | `false` | 响应中是否包含中间态 JSON |
| `return_model_output` | bool | `false` | 响应中是否包含模型原始输出 JSON |
| `return_content_list` | bool | `false` | 响应中是否包含内容列表 JSON |
| `return_images` | bool | `false` | 响应中是否包含提取出的图片 |
| `response_format_zip` | bool | **`true`**（本项目默认，官方接口默认 `false`） | 是否以 ZIP 文件形式返回结果。为 `false` 时返回 JSON |
| `return_original_file` | bool | `false` | ZIP 结果中是否包含处理后的原始文件，仅 `response_format_zip=true` 时生效 |
| `client_side_output_generation` | bool | `false` | 是否把最终 Markdown/内容列表的生成推迟到客户端处理 |
| `start_page_id` | int | `0` | 起始页码，从 0 开始 |
| `end_page_id` | int | `99999` | 结束页码，从 0 开始 |

`mineru_get_task_status` 和 `mineru_get_task_result` 只有一个参数：

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `task_id` | string | 必填 | 由 `mineru_submit_task` 返回的任务 ID |

### backend 可选值

| 值 | 说明 |
|---|---|
| `pipeline` | 通用后端，支持多语言，无幻觉 |
| `vlm-engine` | 本地算力，高精度，仅支持中英文 |
| `vlm-http-client` | 远程算力（OpenAI 兼容服务），高精度，仅支持中英文 |
| `hybrid-engine`（默认） | 本地算力，混合解析，支持多语言，用 `effort` 调节精度 |
| `hybrid-http-client` | 远程算力为主、需少量本地算力，混合解析，支持多语言 |

### lang_list 可选值

`ch`（中英日繁拉丁）、`ch_server`、`korean`、`ta`（泰米尔语）、`te`（泰卢固语）、`ka`（卡纳达语）、`th`（泰语）、`el`（希腊语）、`arabic`、`east_slavic`、`cyrillic`、`devanagari`。仅 `pipeline` 后端生效，其他后端会忽略此参数。

## 服务端配置（环境变量）

以下是 server 启动时的固定配置，不是接口参数，写在 MCP 配置的 `env` 字段里。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MINERU_API_URL` | `http://localhost:8000` | MinerU 服务地址 |
| `MINERU_OUTPUT_DIR` | 无（必须设置） | 解析结果保存目录，绝对路径。不设置时调用解析工具会直接报错 |
| `MINERU_API_TIMEOUT` | `600` | 请求超时秒数，大文件超时可调大 |
| `MCP_TRANSPORT` | `stdio` | 传输模式：`stdio`（本地子进程）或 `streamable-http`（远程服务） |
| `MCP_HOST` | `127.0.0.1` | 仅 HTTP 模式生效，监听地址，设为 `0.0.0.0` 可对外暴露 |
| `MCP_PORT` | `8001` | 仅 HTTP 模式生效，监听端口 |

## 远程部署（可选）

如果想把 MCP 服务架在一台机器上，让多个客户端远程连接，用 HTTP 模式启动：

```bash
MCP_TRANSPORT=streamable-http MCP_PORT=8001 MINERU_OUTPUT_DIR=/data/mineru-output mineru-docparse-mcp
```

客户端这边改成连 URL：

```json
{
  "mcpServers": {
    "mineru": {
      "type": "streamableHttp",
      "url": "http://<服务器地址>:8001/mcp"
    }
  }
}
```

不写 `MCP_TRANSPORT` 时默认是本地 stdio 模式（上面「配置到 Claude Code」那种），日常个人使用用默认模式就够了。

## 常见问题

**提示"服务未配置 MINERU_OUTPUT_DIR 环境变量"** — 这是必需的服务端配置，不是接口参数，需要在 MCP 配置的 `env` 里设置好之后重启一下 MCP 连接。

**提示"无法连接 MinerU 服务"** — 确认 `MINERU_API_URL` 能访问：`curl $MINERU_API_URL/health`。stdio 模式下环境变量要写在 MCP 配置的 `env` 里，写在自己终端的 `export` 里不生效。

**大文件一直超时** — 换 `mineru_submit_task` 走后台任务，或调大 `MINERU_API_TIMEOUT`。

**想要 JSON 而不是 ZIP** — 调用时把 `response_format_zip` 设为 `false`，结果会存成 `.json` 而不是 `.zip`。

## License

MIT
