# mineru-docparse-mcp

MCP Server that converts Word / PDF / PPT / Excel to Markdown, powered by the [MinerU DocParse API](https://github.com/opendatalab/MinerU).

> This project is a protocol wrapper — it does not parse documents itself. You need a running MinerU DocParse service, defaulting to `http://localhost:8000`. See the [MinerU repository](https://github.com/opendatalab/MinerU) for deployment instructions.

## Installation

```bash
pip install mineru-docparse-mcp
```

## Setup with Claude Code

The output directory is a server-side setting (not a per-request parameter), so `MINERU_OUTPUT_DIR` must be configured in advance:

```json
{
  "mcpServers": {
    "mineru": {
      "command": "uvx",
      "args": ["mineru-docparse-mcp"],
      "env": {
        "MINERU_API_URL": "http://localhost:8000",
        "MINERU_OUTPUT_DIR": "/Users/yourname/Documents/mineru-output"
      }
    }
  }
}
```

Once configured, Claude will automatically invoke the tools below. All parsed results are saved to `MINERU_OUTPUT_DIR`.

## Tools

| Tool | Description |
|---|---|
| `mineru_parse_document` | Convert PDF/Word/PPT/Excel to Markdown, saved to disk |
| `mineru_health_check` | Check MinerU service health |

**Output format**: Results are saved exactly as returned by MinerU. When `response_format_zip=true` (the default) output is saved as `.zip`; when `false` as `.json`. File name matches the source file — if a file with the same name already exists, a timestamp is appended to avoid overwriting.

## API Parameters

`mineru_parse_document` mirrors the MinerU `/file_parse` endpoint:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file_path` | string | required | Local document path (absolute or relative) |
| `backend` | enum | `hybrid-engine` | Parsing backend, see "backend options" below |
| `lang_list` | string[] | `["ch"]` | OCR language list, only for `pipeline` backend |
| `effort` | `medium` \| `high` | `medium` | `hybrid` backends only. `medium`: faster, no chart analysis; `high`: higher accuracy with chart analysis, slower |
| `parse_method` | `auto` \| `txt` \| `ocr` | `auto` | PDF parsing method for `pipeline`/`hybrid`: auto-detect / text extraction / OCR |
| `formula_enable` | bool | `true` | Enable formula parsing (LaTeX) |
| `table_enable` | bool | `true` | Enable table parsing |
| `image_analysis` | bool | `true` | Enable image/chart analysis (VLM/hybrid backends only) |
| `server_url` | string \| null | `null` | OpenAI-compatible server URL, required for `*-http-client` backends |
| `return_md` | bool | `true` | Include Markdown content in response |
| `return_middle_json` | bool | `false` | Include intermediate JSON in response |
| `return_model_output` | bool | `false` | Include raw model output JSON in response |
| `return_content_list` | bool | `false` | Include content list JSON in response |
| `return_images` | bool | `false` | Include extracted images in response |
| `response_format_zip` | bool | **`true`** (this project's default; API default is `false`) | Return results as ZIP (false returns JSON) |
| `return_original_file` | bool | `false` | Include processed original file in ZIP (`response_format_zip=true` only) |
| `client_side_output_generation` | bool | `false` | Defer final Markdown/content-list generation to the client |
| `start_page_id` | int | `0` | Starting page (0-indexed) |
| `end_page_id` | int | `99999` | Ending page (0-indexed) |

### Backend Options

| Value | Description |
|---|---|
| `pipeline` | General-purpose, multilingual, no hallucination |
| `vlm-engine` | Local compute, high accuracy, Chinese/English only |
| `vlm-http-client` | Remote compute (OpenAI-compatible), high accuracy, Chinese/English only |
| `hybrid-engine` (default) | Local compute, hybrid parsing, multilingual, tune with `effort` |
| `hybrid-http-client` | Primarily remote compute + light local, hybrid parsing, multilingual |

### Language Options (`lang_list`)

`ch` (Chinese/English/Japanese/Traditional/Latin), `ch_server`, `korean`, `ta` (Tamil), `te` (Telugu), `ka` (Kannada), `th` (Thai), `el` (Greek), `arabic`, `east_slavic`, `cyrillic`, `devanagari`. Only applies to the `pipeline` backend; ignored by others.

## Server Configuration (Environment Variables)

These are server startup settings — configure them in the `env` field of your MCP config, not as per-request parameters.

| Variable | Default | Description |
|---|---|---|
| `MINERU_API_URL` | `http://localhost:8000` | MinerU service URL |
| `MINERU_OUTPUT_DIR` | none (required) | Directory for parsed results (absolute or relative paths) |
| `MINERU_API_TIMEOUT` | `600` | Request timeout in seconds — increase for large files |
| `MCP_TRANSPORT` | `stdio` | Transport mode: `stdio` (local subprocess) or `streamable-http` (remote) |
| `MCP_HOST` | `127.0.0.1` | Listen address (HTTP mode only); set to `0.0.0.0` to expose externally |
| `MCP_PORT` | `8001` | Listen port (HTTP mode only) |

## Remote Deployment (Optional)

To run the MCP server on a dedicated machine accessible by multiple clients, use HTTP mode:

```bash
MCP_TRANSPORT=streamable-http MCP_PORT=8001 MINERU_OUTPUT_DIR=/data/mineru-output uvx mineru-docparse-mcp
```

Clients connect via URL:

```json
{
  "mcpServers": {
    "mineru": {
      "type": "streamableHttp",
      "url": "http://<server-address>:8001/mcp"
    }
  }
}
```

Omitting `MCP_TRANSPORT` defaults to local stdio mode (the "Setup with Claude Code" flow above), which is sufficient for personal use.

## FAQ

**"MINERU_OUTPUT_DIR environment variable not configured"** — This is a required server setting, not an API parameter. Set it in the `env` field of your MCP config and restart the MCP connection.

**"Cannot connect to MinerU service"** — Verify `MINERU_API_URL` is reachable: `curl $MINERU_API_URL/health`. In stdio mode, environment variables must be set in the MCP config `env` field; shell `export` won't work.

**Large files timeout** — Increase `MINERU_API_TIMEOUT` or narrow the `start_page_id`/`end_page_id` range to parse in batches.

**Want JSON instead of ZIP** — Set `response_format_zip` to `false`; results will be saved as `.json` instead of `.zip`.

## License

MIT
