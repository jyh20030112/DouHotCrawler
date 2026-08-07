# DouHotCrawler FastAPI API 文档

本文档描述 `douhot_crawler/api/` 当前实现的 HTTP API，适用于接口调用方、联调人员和服务运维人员。

## 1. 服务概览

| 项目 | 说明 |
| --- | --- |
| API 版本 | `v1` |
| 路径前缀 | `/api/v1` |
| 默认监听地址 | `http://127.0.0.1:8000` |
| 数据格式 | JSON，UTF-8 |
| 身份认证 | 当前未启用 |
| 交互文档 | `/docs` |
| OpenAPI JSON | `/openapi.json` |
| 执行模型 | SQLite 持久化全局 FIFO 队列，单 Worker 串行执行 |
| 调度时区 | `Asia/Shanghai` |

> 当前接口没有身份认证。不要直接暴露到公网；部署时应通过防火墙、反向代理、TLS 和访问控制限制调用来源。

## 2. 核心调用约定

### 2.1 异步任务与关键词采集

`crawl`、`analyze`、`upload` 和 `pipeline` 都是异步任务接口。创建成功返回 HTTP `202 Accepted`，仅表示任务已经进入队列，并不表示任务已经执行完成。

`POST /api/v1/viral-videos/collect` 是混合模式接口：只要求 `keyword`。不传 `callback_url` 时 HTTP 请求等待 FIFO 任务执行完成并直接返回最终数组；传入 `callback_url` 时立即返回 `202` 和 `task_id`，后台完成后向回调地址 POST 同一个数组。

标准调用流程：

1. 调用任务创建接口。
2. 保存响应中的 `task_id`。
3. 轮询 `GET /api/v1/tasks/{task_id}`。
4. 等待任务进入终态。

终态包括：

- `succeeded`
- `succeeded_with_warnings`
- `failed`

`paused` 不是终态，需要调用恢复接口后才会继续执行。

### 2.2 FIFO 串行队列

所有任务共用一个持久化队列，按照创建时间先进先出，同一时间只执行一个任务：

```text
HTTP 创建任务
    ↓
SQLite: queued
    ↓
单 Worker 领取
    ↓
running
    ↓
succeeded / succeeded_with_warnings / failed / paused
```

服务必须保持运行，后台 Worker 才能领取任务。`DOUHOT_API_WORKERS` 固定为 `1`，不能通过启动多个 Uvicorn Worker 扩大并发。

### 2.3 请求头

有 JSON 请求体的接口应发送：

```http
Content-Type: application/json
Accept: application/json
```

### 2.4 时间格式

任务的 `created_at`、`updated_at`、`started_at` 和 `finished_at` 使用 UTC ISO 8601 时间。每日调度字段 `scheduler_next_run_at` 使用带 `+08:00` 偏移的上海时间。

## 3. 启动与配置

### 3.1 启动服务

```bash
uv sync
uv run playwright install chromium
uv run douhot-api
```

启动后访问：

```text
http://127.0.0.1:8000/docs
```

实际地址由 `DOUHOT_API_HOST` 和 `DOUHOT_API_PORT` 决定。

### 3.2 必要环境变量

| 环境变量 | 说明 |
| --- | --- |
| `DOUHOT_HOTSPOT_API_URL` | 热点关键词外部接口完整 URL |
| `DOUHOT_INDUSTRY_API_URL` | 行业关键词外部接口完整 URL |
| `DOUHOT_COOKIE_API_URL` | Cookie 配置外部接口完整 URL |
| `DOUHOT_RANKING_API_URL` | 榜单数据接收外部接口完整 URL |
| `DOUHOT_INDUSTRY_RANKING_API_URL` | 行业榜单数据接收外部接口完整 URL |
| `EXTRACT_API_URL` | 视频口播提取接口完整 URL |
| `DOUHOT_HOTSPOT_OPEN_ID` | 获取热点关键词时发送的 `openId` |

这些配置缺失或 URL 格式无效时，服务会在启动阶段校验失败。

### 3.3 可选环境变量

| 环境变量 | 默认值 | 约束与用途 |
| --- | --- | --- |
| `DOUHOT_HOTSPOT_SIZE` | `30` | 热点关键词数量，范围 `1～30` |
| `DOUHOT_INDUSTRY_SIZE` | `30` | 行业关键词数量，范围 `1～30` |
| `DOUHOT_API_DATA_ROOT` | 系统应用数据目录下的 `DouHotCrawler/api` | SQLite、Excel 和任务日志目录；相对路径按服务工作目录解析 |
| `DOUHOT_API_HOST` | `127.0.0.1` | API 监听地址 |
| `DOUHOT_API_PORT` | `8000` | API 监听端口，范围 `1～65535` |
| `DOUHOT_API_WORKERS` | `1` | 必须为 `1` |
| `DOUHOT_MAX_VIDEOS_PER_KEYWORD` | `3` | pipeline 每个关键词的有效口播目标；单独 crawl/collect 的默认采集上限，范围 `1～500` |
| `DOUHOT_MAX_CANDIDATES_PER_KEYWORD` | `15` | pipeline 每个关键词最多爬取的候选视频数，范围 `1～500` |
| `DOUHOT_DAILY_ENABLED` | `true` | 是否启用 FastAPI 内置每日调度 |
| `DOUHOT_DAILY_TIME` | `03:00` | 上海时区触发时间，格式 `HH:MM` |
| `DOUHOT_DAILY_API_URL` | `http://127.0.0.1:8000` | 仅供 `douhot-daily` 手动触发命令调用 |
| `CONNECT_TIMEOUT_SECONDS` | `10` | 外部 HTTP 接口连接超时秒数 |
| `READ_TIMEOUT_SECONDS` | `90` | 外部 HTTP 接口读取超时秒数 |
| `ARTIFACT_RETENTION_DAYS` | `3` | Excel 和任务日志保留天数 |
| `METADATA_RETENTION_DAYS` | `7` | 终态 SQLite 任务元数据保留天数 |

发送批次固定为每批 `20` 条，目前不是可配置项。

## 4. 接口总览

| 方法 | 路径 | 成功状态码 | 用途 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/health` | `200` | 检查服务、浏览器、SQLite 和调度器状态 |
| `GET` | `/api/v1/keywords` | `200` | 获取热点关键词 |
| `POST` | `/api/v1/viral-videos/collect` | `200` / `202` | 按关键词爬取、解析并直接返回或回调榜单数组 |
| `POST` | `/api/v1/tasks/crawl` | `202` | 创建单关键词爬取任务 |
| `POST` | `/api/v1/tasks/analyze` | `202` | 为爬取任务的 Excel 补充视频口播和播放地址 |
| `POST` | `/api/v1/tasks/upload` | `202` | 上传已有 Excel 中的全部合格数据 |
| `POST` | `/api/v1/tasks/pipeline` | `202` | 创建爬取、口播、发送完整流水线 |
| `GET` | `/api/v1/tasks/{task_id}` | `200` | 查询任务状态、进度和结果 |
| `POST` | `/api/v1/tasks/{task_id}/pause` | `200` | 安全暂停任务 |
| `POST` | `/api/v1/tasks/{task_id}/resume` | `200` | 恢复暂停任务 |

## 5. 健康检查

### `GET /api/v1/health`

该接口不调用外部关键词、Cookie、口播或发送服务。

请求示例：

```bash
curl -X GET 'http://127.0.0.1:8000/api/v1/health' \
  -H 'Accept: application/json'
```

响应示例：

```json
{
  "status": "ok",
  "worker_running": true,
  "database_ok": true,
  "browser_ok": true,
  "external_urls_configured": true,
  "scheduler_overlap": false,
  "scheduler_enabled": true,
  "scheduler_time": "03:00",
  "scheduler_timezone": "Asia/Shanghai",
  "scheduler_next_run_at": "2026-08-08T03:00:00+08:00"
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `status` | string | `ok` 或 `degraded`；SQLite 不可用或浏览器不可用时为 `degraded` |
| `worker_running` | boolean | FIFO Worker 是否正在运行 |
| `database_ok` | boolean | SQLite 连接检查是否成功 |
| `browser_ok` | boolean | 启动服务时是否检测到可用 Chromium、Chrome 或 Edge |
| `external_urls_configured` | boolean | 外部 URL 已通过启动配置校验；当前正常启动后为 `true` |
| `scheduler_overlap` | boolean | 是否存在 `queued/running/pausing/paused` 的 pipeline；不是配置项 |
| `scheduler_enabled` | boolean | 内置每日调度是否启用 |
| `scheduler_time` | string | 每日触发时间 |
| `scheduler_timezone` | string | 固定为 `Asia/Shanghai` |
| `scheduler_next_run_at` | string/null | 下一次触发时间；调度关闭时为 `null` |

如果服务启动后才安装浏览器，需要重启 FastAPI，健康检查中的浏览器状态才会重新检测。

## 6. 获取热点关键词

### `GET /api/v1/keywords`

服务调用 `DOUHOT_HOTSPOT_API_URL`，发送：

```json
{
  "openId": "由 DOUHOT_HOTSPOT_OPEN_ID 配置",
  "size": 30
}
```

服务从外部响应的 `data.records[*].title` 提取关键词，去除空值、去除首尾空格、按原顺序去重。

请求示例：

```bash
curl -X GET 'http://127.0.0.1:8000/api/v1/keywords' \
  -H 'Accept: application/json'
```

响应示例：

```json
{
  "key_word": [
    "mj是什么网络梗",
    "mj是什么意思",
    "果园精选好物"
  ]
}
```

该接口同步调用外部服务。外部接口网络失败、业务状态码失败或响应结构错误时直接返回 HTTP `502`。

## 7. 按关键词采集并返回榜单数据

> 独立接入文档：[关键词视频采集接口接入文档](VIRAL_VIDEOS_COLLECT_API.md)

### `POST /api/v1/viral-videos/collect`

该接口按单个关键词串行执行爬取和口播解析，生成与外部 `rankingViralVideo` 接口请求体完全一致的 JSON 数组。它只返回或回调数据，不会调用 `DOUHOT_RANKING_API_URL`。

请求体只有 `keyword` 必填：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `keyword` | string | 是 | 无 | 搜索关键词，去除首尾空格后长度 `1～200` |
| `result_type` | string | 否 | `低粉爆款` | 榜单类型，与 crawl 接口相同 |
| `time_range` | string | 否 | `近7天` | 榜单时间范围，与 crawl 接口相同 |
| `input_timeout` | number | 否 | `30` | 等待搜索框的最长秒数，`0 < value <= 300` |
| `detail_delay` | number | 否 | `1` | 两条详情之间的基础等待秒数，范围 `0～60` |
| `limit` | integer/null | 否 | `null` | `1～500`；省略或传 `null` 时读取 `DOUHOT_MAX_VIDEOS_PER_KEYWORD` |
| `analyze_timeout` | number | 否 | `90` | 单条口播提取请求超时秒数，`0 < value <= 600` |
| `analyze_delay` | number | 否 | `0` | 两条口播提取请求之间的等待秒数，范围 `0～60` |
| `callback_url` | HTTP(S) URL/null | 否 | `null` | 提供时启用异步回调；只允许 `http` 或 `https` URL |

最简同步请求：

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/viral-videos/collect' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{"keyword":"大健康"}'
```

不传 `callback_url` 时，请求进入全局 FIFO 队列并保持 HTTP 连接，直到完成后返回 HTTP `200`：

```json
[
  {
    "type": 0,
    "keyword": "大健康",
    "videoName": "野外求生第一天",
    "videoUrl": "https://www.douyin.com/video/7664192779984419999",
    "authorName": "贝爷求生",
    "followerCount": 12000,
    "heatValue": "50.2万",
    "newPlayCount": "210.3万",
    "newLikeCount": "12.1万",
    "likeRate": "5.75%",
    "highPraiseComment": "太硬核了(2万赞)",
    "videoOral": "今天教大家野外如何取火……",
    "videoPlayUrl": "https://aweme.snssdk.com/aweme/v1/play/?video_id=v0200..."
  }
]
```

同步模式可能等待数分钟，也可能排在正在运行的每日流水线之后。部署反向代理时，需要相应调高读取超时。

异步回调请求：

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/viral-videos/collect' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "keyword":"大健康",
    "callback_url":"https://example.com/hooks/douhot"
  }'
```

接口立即返回 HTTP `202`：

```json
{
  "task_id": "42118d44-6334-4a0c-a9a5-9a5096ab2962",
  "status": "queued",
  "created": true
}
```

任务成功后，服务向 `callback_url` 发起 `POST`，body 就是同步模式的最终 JSON 数组，并携带：

```http
Content-Type: application/json
X-DouHot-Task-ID: 42118d44-6334-4a0c-a9a5-9a5096ab2962
```

回调的任意 `2xx` 响应都视为成功。网络错误、`429` 和 `5xx` 按 `0、2、5、10` 秒间隔最多尝试 4 次；重定向和其他非 `2xx` 响应视为失败。回调接收方应使用 `X-DouHot-Task-ID` 做幂等处理，避免重试产生重复数据。回调最终失败时 collect 任务进入 `failed`，不会改为调用榜单上传接口，也不会向回调地址发送另一种错误结构，可使用返回的 `task_id` 查询失败原因。

数据规则：

- `keyword` 保留请求提供的原始值，不使用可能被替换或截断的 Excel Sheet 名。
- `videoUrl` 是抖音分享链接，`videoPlayUrl` 是提取接口返回的直接播放地址。
- `followerCount` 固定为整数，无法解析或为空时按 `0` 返回并记录 warning。
- 缺少视频名称、分享链接、博主名称或视频口播的记录会跳过。
- 没有搜索结果时正常返回或回调空数组 `[]`。
- 部分口播失败时返回其余成功记录；已爬到视频但所有口播均失败时任务失败。

## 8. 创建单关键词爬取任务

### `POST /api/v1/tasks/crawl`

该接口只执行单关键词爬取并生成 Excel，不会提取口播，也不会发送数据库。

请求体：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `keyword` | string | 是 | 无 | 搜索关键词，同时用于 Excel Sheet 名，长度 `1～200` |
| `result_type` | string | 否 | `低粉爆款` | `低粉爆款`、`视频总榜`、`高完播率`、`高涨粉率`、`高点赞率` |
| `time_range` | string | 否 | `近7天` | `近1小时`、`近1天`、`近3天`、`近7天` |
| `input_timeout` | number | 否 | `30` | 等待搜索框的最长秒数，`0 < value <= 300` |
| `detail_delay` | number | 否 | `1` | 两条详情之间的基础等待秒数，范围 `0～60`，实际存在小幅随机抖动 |
| `limit` | integer/null | 否 | `null` | 采集上限，范围 `1～500`；`null` 使用环境变量默认值 |

请求示例：

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/tasks/crawl' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "keyword": "大健康",
    "result_type": "低粉爆款",
    "time_range": "近7天",
    "input_timeout": 30,
    "detail_delay": 1,
    "limit": 3
  }'
```

响应：

```json
{
  "task_id": "42118d44-6334-4a0c-a9a5-9a5096ab2962",
  "status": "queued",
  "created": true
}
```

执行链路：

1. 任务参数写入 SQLite，状态为 `queued`。
2. Worker 按 FIFO 顺序将任务改为 `running`。
3. 实时调用 Cookie 接口，请求 `{"type": 0}`。
4. 在无持久化 Profile 的临时浏览器上下文中注入 Cookie。
5. 打开热点宝、搜索关键词、选择榜单类型和时间范围。
6. 逐条采集视频信息、视频 ID 和高赞评论。
7. 每页增量写入任务专属 Excel。
8. 完成后写入结果元数据并进入终态。

Excel 路径：

```text
DOUHOT_API_DATA_ROOT/tasks/{task_id}/result.xlsx
```

同一 Sheet 以“视频名称 + 博主名称”去重。Sheet 名中的 Excel 非法字符会替换为 `_`，最终名称最多 31 个字符。

成功结果示例：

```json
{
  "excel_path": "/data/api/tasks/42118d44-6334-4a0c-a9a5-9a5096ab2962/result.xlsx",
  "added_count": 3,
  "skipped_count": 0,
  "sheet": "大健康",
  "stopped": false,
  "artifact": {
    "path": "tasks/42118d44-6334-4a0c-a9a5-9a5096ab2962/result.xlsx",
    "row_count": 3,
    "sha256": "文件SHA-256"
  }
}
```

## 9. 创建口播提取任务

### `POST /api/v1/tasks/analyze`

该接口为一个已经成功的 `crawl` 任务补充视频口播和视频播放地址，直接更新原爬取任务的 Excel，不创建新的 Excel 副本。原来的“视频的url”继续保存抖音分享链接，新接口返回的 `video_url` 写入“视频播放地址”。

前置条件：

- `crawl_task_id` 必须存在。
- 对应任务类型必须是 `crawl`。
- 对应任务状态必须为 `succeeded` 或 `succeeded_with_warnings`。
- 原任务的 `result.xlsx` 必须存在且未被其他进程占用。

请求体：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `crawl_task_id` | string | 是 | 无 | 已成功 crawl 任务的 36 字符 UUID |
| `sheets` | string[]/null | 否 | `null` | 指定 Sheet；`null` 表示全部 Sheet，会去空和去重 |
| `timeout` | number | 否 | `90` | 单条口播提取 HTTP 请求超时秒数，`0 < value <= 600` |
| `delay` | number | 否 | `0` | 两条口播请求之间的等待秒数，范围 `0～60` |
| `limit` | integer/null | 否 | `null` | 最多处理多少条待提取记录；`null` 表示全部 |
| `overwrite` | boolean | 否 | `false` | 是否覆盖已经存在的口播和视频播放地址 |

请求示例：

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/tasks/analyze' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "crawl_task_id": "42118d44-6334-4a0c-a9a5-9a5096ab2962",
    "sheets": ["大健康"],
    "timeout": 90,
    "delay": 0,
    "limit": null,
    "overwrite": false
  }'
```

执行时服务实时调用 Cookie 配置接口，请求：

```json
{
  "type": 1
}
```

随后逐行调用 `EXTRACT_API_URL`，从成功响应中读取 `transcript` 和 `video_url`，分别写入“视频口播”和“视频播放地址”。播放地址单元格设置为可点击超链接。单条提取失败不会中断整个任务，而是累计 `failed` 和 warning，并继续下一行。

兼容旧 Excel：当口播已经存在但“视频播放地址”为空时，即使 `overwrite=false` 也会重新请求一次以补齐播放地址；只有两列都已有值时才跳过。

成功结果示例：

```json
{
  "succeeded": 2,
  "skipped": 1,
  "failed": 1,
  "artifact": {
    "path": "tasks/42118d44-6334-4a0c-a9a5-9a5096ab2962/result.xlsx",
    "row_count": 4,
    "sha256": "文件SHA-256"
  }
}
```

当 `failed > 0` 时，任务通常进入 `succeeded_with_warnings`，详细警告可以在任务的 `progress.warnings` 中查看。

## 10. 上传现有 Excel

### `POST /api/v1/tasks/upload`

该接口读取已有任务对应的 Excel，把所有合格行发送到 `DOUHOT_RANKING_API_URL`。

请求体：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `source_task_id` | string | 是 | 无 | `crawl`、`analyze` 或 `pipeline` 任务 UUID |
| `sheets` | string[]/null | 否 | `null` | 只上传指定 Sheet；`null` 表示全部 Sheet |

`source_task_id` 的解析规则：

- `crawl`：使用该 crawl 自己的 Excel。
- `pipeline`：使用该 pipeline 自己的 Excel。
- `analyze`：使用其 `crawl_task_id` 对应的原始 Excel。
- 源任务处于 `queued`、`running` 或 `pausing` 时返回 HTTP `409`。
- 源任务是 `paused` 或 `failed` 时，只要 Excel 已存在，也允许上传。

请求示例：

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/tasks/upload' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "source_task_id": "42118d44-6334-4a0c-a9a5-9a5096ab2962",
    "sheets": null
  }'
```

合格行必须同时存在以下字段：

- 视频名称
- 视频 URL
- 博主名称
- 视频口播

缺少任意一个字段的行会跳过，不发送。发送字段映射如下：

| 发送字段 | Excel 字段 | 类型与处理 |
| --- | --- | --- |
| `type` | 固定值 | 整数 `0` |
| `keyword` | Sheet 名 | string |
| `videoName` | 视频名称 | string |
| `videoUrl` | 视频的url | string |
| `videoPlayUrl` | 视频播放地址 | string；旧 Excel 缺少该列时发送空字符串 |
| `authorName` | 博主名称 | string |
| `followerCount` | 总粉丝数 | integer；支持千、万、亿，无法解析时按 `0` 发送并记录 warning |
| `heatValue` | 热度值 | string |
| `newPlayCount` | 新增播放量 | string |
| `newLikeCount` | 新增点赞量 | string |
| `likeRate` | 点赞率 | string |
| `highPraiseComment` | 高赞评论 | string，可为空 |
| `videoOral` | 视频口播 | string |

外部发送请求体是数组，每批固定最多 20 条：

```json
[
  {
    "type": 0,
    "keyword": "求生",
    "videoName": "野外求生第一天",
    "videoUrl": "https://www.douyin.com/video/7664192779984419999",
    "videoPlayUrl": "https://aweme.snssdk.com/aweme/v1/play/?video_id=v0200...",
    "authorName": "贝爷求生",
    "followerCount": 12000,
    "heatValue": "50.2万",
    "newPlayCount": "210.3万",
    "newLikeCount": "12.1万",
    "likeRate": "5.75%",
    "highPraiseComment": "太硬核了(2万赞)",
    "videoOral": "今天教大家野外如何取火……"
  }
]
```

成功结果示例：

```json
{
  "sheets": ["大健康", "美容"],
  "eligible_rows": 40,
  "sent_rows": 40,
  "artifact": {
    "path": "tasks/源任务ID/result.xlsx",
    "row_count": 45,
    "sha256": "文件SHA-256"
  }
}
```

发送成功记录会保存在 SQLite。上传失败时任务自动进入：

```text
pausing → paused
pause_reason = upload_failure
```

调用恢复接口后，只重发当前上传任务中尚未成功的记录。新建另一个 upload 任务会拥有新的发送记录空间，可能再次提交相同 Excel 数据。

## 11. 创建完整流水线

### `POST /api/v1/tasks/pipeline`

该接口是每日定时任务和完整自动化流程的主要入口。`data_source`
默认为 `all`，整体顺序固定为：

```text
热点榜：获取热点关键词
  ↓
热点关键词 1：爬取 → 口播 → rankingViralVideo
  ↓
热点关键词 2：爬取 → 口播 → rankingViralVideo
  ↓
热点榜全部结束
  ↓
行业榜：获取行业关键词
  ↓
行业关键词 1：爬取 → 口播 → rankingViralVideoByIndustry
  ↓
行业关键词 2：爬取 → 口播 → rankingViralVideoByIndustry
```

数据源之间、关键词之间、关键词内部阶段之间均不并发。每个关键词只爬取一批候选；
爬取保存并释放 Excel 文件锁后，口播提取才开始，因此不会在浏览器阶段内嵌套 Excel 锁。

两类数据源的外部请求映射：

| 数据源 | 取词配置 | 取词请求体 | 上传配置 |
| --- | --- | --- | --- |
| `hotspot` | `DOUHOT_HOTSPOT_API_URL` | `{"openId":"...","size":DOUHOT_HOTSPOT_SIZE}` | `DOUHOT_RANKING_API_URL` |
| `industry` | `DOUHOT_INDUSTRY_API_URL` | `{"openId":"...","size":DOUHOT_INDUSTRY_SIZE}` | `DOUHOT_INDUSTRY_RANKING_API_URL` |

两个取词接口共用 `DOUHOT_HOTSPOT_OPEN_ID`，都从 `data.records[*].title`
提取关键词。两个上传接口的请求体都是榜单数组，字段完全相同，包含
`videoPlayUrl`，每批固定 20 条。

请求体：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `data_source` | `hotspot` / `industry` / `all` | 否 | `all` | 只跑热点榜、只跑行业榜，或先热点后行业全部执行 |
| `keywords` | string[]/null | 否 | `null` | 自定义关键词，最多 30 个；仅能用于单一数据源；`all` 时必须为 `null` |
| `result_type` | string | 否 | `低粉爆款` | 所有关键词使用的榜单类型 |
| `time_range` | string | 否 | `近7天` | 所有关键词使用的时间范围 |
| `input_timeout` | number | 否 | `30` | 等待搜索框秒数，`0 < value <= 300` |
| `detail_delay` | number | 否 | `1` | 两条视频详情之间的基础等待秒数，范围 `0～60` |
| `limit_per_keyword` | integer/null | 否 | `null` | 每个关键词最终需要的有效口播条数，范围 `1～500`；`null` 使用 `DOUHOT_MAX_VIDEOS_PER_KEYWORD`，默认 3 |
| `candidate_limit_per_keyword` | integer/null | 否 | `null` | 每个关键词最多爬取的候选视频数，范围 `1～500`；`null` 使用 `DOUHOT_MAX_CANDIDATES_PER_KEYWORD`，默认 15；不能小于有效口播目标 |
| `overwrite_transcript` | boolean | 否 | `false` | 恢复时是否覆盖已有口播 |

默认完整任务（热点榜 + 行业榜）：

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/tasks/pipeline' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{"data_source":"all"}'
```

指定关键词：

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/tasks/pipeline' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "data_source": "hotspot",
    "keywords": ["大健康", "美容"],
    "limit_per_keyword": 3,
    "candidate_limit_per_keyword": 15,
    "overwrite_transcript": false
  }'
```

防重复规则：如果已经存在状态为 `queued`、`running`、`pausing` 或 `paused` 的 pipeline：

- 所有请求参数完全相同：返回已有任务，`created=false`。
- 参数不同：返回 HTTP `409` 和 `PIPELINE_ALREADY_ACTIVE`，避免调用方误以为新参数已生效。

相同请求响应：

```json
{
  "task_id": "已有流水线任务ID",
  "status": "running",
  "created": false
}
```

每个关键词的固定执行规则如下：

1. 最多爬取 `candidate_limit_per_keyword` 条候选，默认 15 条。
2. 按 Excel 行顺序串行提取口播，空口播和单条失败不计入成功数。
3. 有效行达到 `limit_per_keyword`（默认 3 条）后立即停止提取剩余候选。
4. 候选耗尽仍不足目标时，上传已有的 1～2 条；0 条时不调用上传接口，并记录 `TARGET_NOT_REACHED`。
5. 上传严格选择前 `limit_per_keyword` 条合格数据，不会因异常上游实现而超发。

恢复时先统计 Excel 中已有的合格数据，只提取剩余数量。视频播放地址允许为空；视频名称、分享 URL、博主名称或口播为空的行仍不具备上传资格。

Pipeline 为每个关键词保存数据源、原关键词、实际 Excel Sheet 名和三个 SQLite 检查点：

- `crawl_done`
- `analyze_done`
- `upload_done`

行业 Sheet 使用稳定的 `行业_...哈希` 名称，因此同名热点关键词与行业关键词不会共用 Excel 数据。发送时的 `keyword` 仍是原关键词。

暂停、恢复或服务重启后，已完成的阶段不会重复执行。上传幂等记录同时区分数据源，同一视频可分别向两个目标发送一次，恢复时不会向同一目标重复发送。升级前的流水线检查点会自动迁移为 `hotspot`。

错误处理规则：

- 单个关键词爬取或分析失败：记录 warning，继续下一个关键词。
- 单条口播失败：记录统计和 warning；没有口播的行在发送阶段跳过。
- 有效口播不足目标：发送已有结果并记录 `TARGET_NOT_REACHED`；0 条时不调用上传接口。
- Cookie 服务不可用，或口播服务重试后仍发生网络、429、401/403、5xx 故障：安全暂停，恢复服务后调用 resume 继续。
- 上传批次失败：整个 pipeline 安全暂停，`pause_reason=upload_failure`。
- 全部关键词都处理失败：任务进入 `failed`，错误为“全部关键词处理失败”。
- 至少一个关键词完成且存在 warning：任务进入 `succeeded_with_warnings`。

成功结果示例：

```json
{
  "keywords_total": 60,
  "keywords_succeeded": 58,
  "keywords_failed": 2,
  "data_source": "all",
  "target_per_keyword": 3,
  "candidate_limit_per_keyword": 15,
  "sources": {
    "hotspot": {"total": 30, "succeeded": 29, "failed": 1},
    "industry": {"total": 30, "succeeded": 29, "failed": 1}
  },
  "artifact": {
    "path": "tasks/流水线任务ID/result.xlsx",
    "row_count": 84,
    "sha256": "文件SHA-256"
  }
}
```

## 12. 查询任务

### `GET /api/v1/tasks/{task_id}`

请求示例：

```bash
curl -X GET \
  'http://127.0.0.1:8000/api/v1/tasks/42118d44-6334-4a0c-a9a5-9a5096ab2962' \
  -H 'Accept: application/json'
```

响应示例：

```json
{
  "task_id": "42118d44-6334-4a0c-a9a5-9a5096ab2962",
  "kind": "crawl",
  "status": "running",
  "phase": "crawl",
  "params": {
    "keyword": "大健康",
    "result_type": "低粉爆款",
    "time_range": "近7天",
    "input_timeout": 30,
    "detail_delay": 1,
    "limit": 3
  },
  "progress": {
    "keyword": "大健康",
    "page": 1,
    "current": 2,
    "added": 2,
    "skipped": 0
  },
  "artifact": null,
  "result": null,
  "error": null,
  "warning_count": 0,
  "pause_reason": null,
  "created_at": "2026-08-07T02:00:00Z",
  "updated_at": "2026-08-07T02:00:20Z",
  "started_at": "2026-08-07T02:00:01Z",
  "finished_at": null
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_id` | string | 任务 UUID |
| `kind` | string | `crawl`、`analyze`、`upload`、`pipeline` 或 `collect` |
| `status` | string | 当前任务状态 |
| `phase` | string/null | 当前阶段，例如 `keywords`、`keyword`、`crawl`、`analyze`、`upload` |
| `params` | object | 创建任务时经过校验和默认值填充的参数 |
| `progress` | object | 动态进度；字段随任务类型和阶段变化 |
| `artifact` | object/null | 成功后返回 Excel 相对路径、总行数和 SHA-256 |
| `result` | object/null | 终态统计结果 |
| `error` | string/null | `failed` 的失败原因；任务执行阶段错误不使用 HTTP 错误信封 |
| `warning_count` | integer | 累计 warning 数量 |
| `pause_reason` | string/null | 常见值：`user`、`shutdown`、`upload_failure` |
| `created_at` | string | 创建时间 |
| `updated_at` | string | 最近更新时间 |
| `started_at` | string/null | 首次开始执行时间 |
| `finished_at` | string/null | 进入终态的时间；暂停时通常为空 |

常见 `progress` 字段：

| 阶段 | 常见字段 |
| --- | --- |
| `keywords` | `current`、`total` |
| `keyword` | `current`、`total`、`keyword` |
| `crawl` | `keyword`、`page`、`current`、`added`、`skipped` |
| `analyze` | `sheet`、`row`、`current`、`succeeded`、`skipped`、`failed` |
| `upload` | `keyword` 或 `sheet`、`current`、`total`、`sent` |
| 任意阶段 | `warnings`，最多保留最近 100 条文本 |

建议轮询间隔为 2～5 秒，不需要高频请求。

## 13. 暂停任务

### `POST /api/v1/tasks/{task_id}/pause`

该接口没有请求体。

```bash
curl -X POST \
  'http://127.0.0.1:8000/api/v1/tasks/42118d44-6334-4a0c-a9a5-9a5096ab2962/pause' \
  -H 'Accept: application/json'
```

状态行为：

| 当前状态 | 结果 |
| --- | --- |
| `queued` | 立即变为 `paused` |
| `running` | 先变为 `pausing`，到安全检查点后变为 `paused` |
| `pausing` | 幂等返回当前状态 |
| `paused` | 幂等返回当前状态 |
| 任意终态 | HTTP `409 TASK_STATE_CONFLICT` |

安全检查点含义：

- 爬取：完成当前视频并写入本页已有数据。
- 口播：完成当前外部提取请求并保存已完成内容。
- 上传：完成当前发送批次。

因此，调用暂停接口后不能只看第一次响应，需要继续查询任务，直到状态真正变为 `paused`。

## 14. 恢复任务

### `POST /api/v1/tasks/{task_id}/resume`

只有 `paused` 状态可以恢复。

```bash
curl -X POST \
  'http://127.0.0.1:8000/api/v1/tasks/42118d44-6334-4a0c-a9a5-9a5096ab2962/resume' \
  -H 'Accept: application/json'
```

恢复后状态先变为 `queued`，再次按 FIFO 顺序等待执行。服务会重新获取对应类型的 Cookie。

恢复依据：

- crawl：读取 Excel 已有行数，继续补足目标数量。
- analyze：保留已有口播，除非请求设置了 `overwrite=true`。
- upload：跳过当前任务中已经成功发送的记录。
- pipeline：读取关键词和三个阶段检查点继续。

对非 `paused` 任务调用恢复接口会返回 HTTP `409 TASK_STATE_CONFLICT`。

## 15. 任务状态机

正常状态流转：

```text
queued → running → succeeded
                 → succeeded_with_warnings
                 → failed
```

用户暂停和恢复：

```text
queued  → paused → queued
running → pausing → paused → queued → running
```

上传失败：

```text
running → paused(upload_failure) → queued → running
```

服务重启时：

- 尚未领取的 `queued` 任务保留，服务启动后继续执行。
- 执行中的 `pipeline` 会重新进入 `queued`，按检查点恢复。
- 执行中的手动 `crawl`、`analyze`、`upload` 会标记为 `failed`，错误为“服务重启，手动任务已终止”。
- 已经 `paused` 的任务继续保持暂停，不会自动恢复。

## 16. 通用响应模型

### 16.1 任务接受响应

```json
{
  "task_id": "任务UUID",
  "status": "queued",
  "created": true
}
```

`created=false` 仅用于 pipeline 防重复场景，表示返回的是已有活动流水线。

### 16.2 Excel 产物

```json
{
  "path": "tasks/{task_id}/result.xlsx",
  "row_count": 90,
  "sha256": "文件SHA-256"
}
```

`path` 相对于 `DOUHOT_API_DATA_ROOT`。当前 API 没有提供 Excel 下载端点，需要服务器侧按该路径读取，或另行通过受保护的文件服务提供下载。

### 16.3 错误响应

所有同步 HTTP 错误使用统一信封：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数校验失败",
    "details": []
  }
}
```

注意区分：

- 创建接口返回前发生的校验或资源冲突，通过 HTTP 4xx/5xx 返回错误信封。
- 已经返回 `202` 后发生的 Cookie、浏览器、口播或发送错误，通过任务查询接口的 `status`、`error`、`warning_count` 和 `progress.warnings` 返回。

## 17. HTTP 错误码

| HTTP 状态码 | `error.code` | 典型场景 |
| --- | --- | --- |
| `400` | `INVALID_SOURCE_TASK` | upload 的源任务类型不支持 |
| `404` | `TASK_NOT_FOUND` | 任务 UUID 不存在 |
| `404` | `ARTIFACT_NOT_FOUND` | 对应 Excel 不存在 |
| `404` | `HTTP_ERROR` | 路由不存在 |
| `409` | `CRAWL_NOT_READY` | analyze 引用的 crawl 尚未成功 |
| `409` | `SOURCE_TASK_BUSY` | upload 的源任务仍在排队或写 Excel |
| `409` | `WORKBOOK_BUSY` | Excel 跨进程文件锁被占用 |
| `409` | `TASK_STATE_CONFLICT` | 当前任务状态不允许暂停或恢复 |
| `409` | `COLLECT_PAUSED` | 同步等待期间 collect 任务被暂停 |
| `422` | `VALIDATION_ERROR` | 请求字段缺失、类型错误、范围错误或出现额外字段 |
| `502` | `EXTERNAL_SERVICE_ERROR` | 热点、Cookie 或榜单外部接口失败 |
| `502` | `COLLECT_FAILED` | 同步 collect 的爬取、解析或结果回调任务失败 |
| `500` | `COLLECT_RESULT_INVALID` | collect 终态没有生成有效结果数组 |
| `500` | `INTERNAL_ERROR` | 未预期的接口处理异常 |

外部服务发生以下情况时可能返回 `EXTERNAL_SERVICE_ERROR`：

- 网络连接失败。
- HTTP `4xx/5xx`。
- 响应不是 JSON。
- 业务 `code != 200`。
- 响应字段结构不符合约定。
- Cookie 字段为空。

外部客户端会对网络错误、HTTP `429`、HTTP `5xx`、业务码 `429` 和业务码 `5xx`重试，等待间隔依次为 `0`、`2`、`5`、`10` 秒，共最多 4 次请求。

## 18. 每日定时任务

每日调度器运行在 `douhot-api` 进程内部：

```dotenv
DOUHOT_DAILY_ENABLED=true
DOUHOT_DAILY_TIME=03:00
```

只要 FastAPI 保持运行，服务会每天上海时区凌晨 3 点尝试创建一个 `data_source=all` 的完整 pipeline。

调度规则：

- 已有活动或暂停 pipeline 时，不重复创建。
- `scheduler_overlap=true` 只表示已有 pipeline，不表示调度器异常。
- 如果服务在计划时间没有运行，之后启动不会自动补跑错过的任务；下一次运行时间会计算为下一天。
- 修改调度配置后需要重启服务。

立即手动触发一次默认 pipeline：

```bash
uv run douhot-daily
```

该命令显式使用 `{"data_source":"all"}` 提交一次任务并退出，不是常驻调度进程。它通过 `DOUHOT_DAILY_API_URL` 调用 `/api/v1/tasks/pipeline`，因此需要 `douhot-api` 正在运行。

## 19. 完整调用示例

### 19.1 Shell 轮询

创建任务：

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/tasks/pipeline' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

保存返回的 `task_id` 后查询：

```bash
curl 'http://127.0.0.1:8000/api/v1/tasks/任务UUID'
```

### 19.2 Python 调用

```python
import time

import httpx


base_url = "http://127.0.0.1:8000"

with httpx.Client(base_url=base_url, timeout=30) as client:
    response = client.post(
        "/api/v1/tasks/pipeline",
        json={"keywords": ["大健康", "美容"], "limit_per_keyword": 3},
    )
    response.raise_for_status()
    task_id = response.json()["task_id"]

    while True:
        task = client.get(f"/api/v1/tasks/{task_id}").json()
        print(task["status"], task["phase"], task["progress"])

        if task["status"] in {
            "succeeded",
            "succeeded_with_warnings",
            "failed",
        }:
            break

        if task["status"] == "paused":
            raise RuntimeError(
                f"任务已暂停：{task['pause_reason']}，需要人工决定是否恢复"
            )

        time.sleep(3)
```

## 20. 文件、锁与保留策略

数据目录示例：

```text
DOUHOT_API_DATA_ROOT/
├── tasks.sqlite3
└── tasks/
    └── {task_id}/
        ├── task.log
        ├── result.xlsx
        └── result.xlsx.lock
```

文件安全机制：

- 同一工作簿使用跨进程非等待文件锁。
- Excel 先写入同目录临时文件，再通过原子替换更新正式文件。
- Cookie 只保存在任务执行内存中，不写入 SQLite、Excel 或日志。

默认清理策略：

- Excel 和任务日志：保留 3 天。
- 终态 SQLite 元数据：保留 7 天。
- 活动任务和暂停任务不会按终态清理规则删除。

清理在 FastAPI 服务启动时执行，不是独立的周期清理进程。

## 21. 运维检查清单

部署后建议依次确认：

1. `GET /api/v1/health` 返回 `worker_running=true`。
2. `database_ok=true`。
3. `browser_ok=true`。
4. `scheduler_enabled` 和 `scheduler_next_run_at` 符合预期。
5. `GET /api/v1/keywords` 能返回关键词。
6. 创建一个 `limit=1` 的 crawl 任务并轮询到成功。
7. 使用该 crawl 任务测试 analyze。
8. 检查 upload 或 pipeline 是否按 20 条分批发送。
9. 通过 systemd、Supervisor 或容器重启策略保证 `douhot-api` 常驻。
