# mineru-docparse-mcp

把 Word / PDF / PPT / Excel 转成 Markdown 的 MCP Server，基于 [MinerU DocParse API](https://github.com/opendatalab/MinerU)。

> 本项目只是协议封装层，本身不解析文档。使用前需要有一个可访问的 MinerU DocParse 服务，默认地址 `http://localhost:8000`。部署方式见 [MinerU 官方仓库](https://github.com/opendatalab/MinerU)。

## 安装

```bash
pip install mineru-docparse-mcp
```

## 配置到 Claude Code

```json
{
  "mcpServers": {
    "mineru": {
      "command": "mineru-docparse-mcp",
      "env": {
        "MINERU_API_URL": "http://localhost:8000"
      }
    }
  }
}
```

配好之后就能用了，Claude 会自动调用下面这些工具。

## 工具

| 工具 | 用途 |
|---|---|
| `mineru_parse_document` | 解析文档，等待完成并直接返回结果（默认用这个） |
| `mineru_submit_task` | 提交大文件到后台解析，立即返回 `task_id` |
| `mineru_get_task_status` | 查询后台任务进度 |
| `mineru_get_task_result` | 后台任务完成后取结果 |
| `mineru_health_check` | 检查 MinerU 服务是否正常 |

普通文件直接说"帮我解析这个 PDF"就行，Claude 会用 `mineru_parse_document`。文件很大（上百页）时会自动改用后台任务的三个工具轮询。

## 常用环境变量

| 变量 | 默认值 | 作用 |
|---|---|---|
| `MINERU_API_URL` | `http://localhost:8000` | MinerU 服务地址 |
| `MINERU_OUTPUT_DIR` | 无 | 解析结果默认保存目录，设置后不用每次都指定路径 |
| `MINERU_API_TIMEOUT` | `600` | 请求超时秒数，大文件超时可调大 |

设置 `MINERU_OUTPUT_DIR` 后，配置就变成这样，之后所有结果都存这里，除非你临时指定别的路径：

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

## 远程部署（可选）

如果想把 MCP 服务架在一台机器上，让多个客户端远程连接，用 HTTP 模式启动：

```bash
MCP_TRANSPORT=streamable-http MCP_PORT=8001 mineru-docparse-mcp
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

不写 `MCP_TRANSPORT` 时默认是本地 stdio 模式（上面"配置到 Claude Code"那种），日常个人使用用默认模式就够了，不需要额外配置。

## 常见问题

**提示"无法连接 MinerU 服务"** — 确认 `MINERU_API_URL` 能访问：`curl $MINERU_API_URL/health`。stdio 模式下环境变量要写在 MCP 配置的 `env` 里，写在自己终端的 `export` 里不生效。

**提示"未指定 output_dir"** — 要么对话里说清楚存哪，要么按上面配置 `MINERU_OUTPUT_DIR`。

**大文件一直超时** — 换 `mineru_submit_task` 走后台任务，或调大 `MINERU_API_TIMEOUT`。

## License

MIT
