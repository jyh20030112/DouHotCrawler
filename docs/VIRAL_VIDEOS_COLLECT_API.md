# 关键词视频采集接口接入文档

本文档只描述以下接口：

```http
POST /api/v1/viral-videos/collect
```

接口接收一个关键词，依次完成热点宝爬取、视频口播解析和数据转换，最终生成与外部 `rankingViralVideo` 接口请求体完全一致的 JSON 数组。

该接口只生成并返回或回调数据，**不会调用榜单数据库上传接口**。

## 1. 接口概览

| 项目 | 说明 |
| --- | --- |
| 方法 | `POST` |
| 路径 | `/api/v1/viral-videos/collect` |
| 请求格式 | `application/json` |
| 身份认证 | 当前未启用 |
| 必填字段 | 只有 `keyword` |
| 可选字段 | 8 个 |
| 同步成功状态码 | `200 OK` |
| 异步受理状态码 | `202 Accepted` |
| 执行方式 | SQLite 持久化全局 FIFO，单 Worker 串行执行 |
| 是否上传数据库 | 否 |

调用前应确认：

- FastAPI 服务正在运行。
- `GET /api/v1/health` 中 `worker_running`、`database_ok` 和 `browser_ok` 为 `true`。
- DouHot Cookie、Douyin Cookie 和视频提取接口配置有效。
- Playwright Chromium 已安装。

下文示例使用：

```text
http://127.0.0.1:28131
```

部署时请替换为实际服务器地址和端口。

## 2. 请求体

### 2.1 字段说明

| 字段 | 类型 | 必填 | 默认值 | 约束与说明 |
| --- | --- | --- | --- | --- |
| `keyword` | string | 是 | 无 | 搜索关键词；去除首尾空格后长度 `1～200` |
| `result_type` | string | 否 | `低粉爆款` | 榜单类型 |
| `time_range` | string | 否 | `近7天` | 榜单时间范围 |
| `input_timeout` | number | 否 | `30` | 等待搜索输入框的最长秒数；`0 < value <= 300` |
| `detail_delay` | number | 否 | `1` | 采集两条详情之间的基础等待秒数；范围 `0～60` |
| `limit` | integer/null | 否 | `null` | 每个关键词最多采集条数；范围 `1～500` |
| `analyze_timeout` | number | 否 | `90` | 单条口播提取请求超时秒数；`0 < value <= 600` |
| `analyze_delay` | number | 否 | `0` | 两条口播提取请求之间的等待秒数；范围 `0～60` |
| `callback_url` | HTTP(S) URL/null | 否 | `null` | 是否启用异步回调 |

`limit` 省略或传 `null` 时，使用环境变量：

```dotenv
DOUHOT_MAX_VIDEOS_PER_KEYWORD=3
```

`result_type` 可选值：

- `低粉爆款`
- `视频总榜`
- `高完播率`
- `高涨粉率`
- `高点赞率`

`time_range` 可选值：

- `近1小时`
- `近1天`
- `近3天`
- `近7天`

请求体不允许出现未定义字段。`callback_url` 只接受 `http` 或 `https` URL。

### 2.2 完整同步请求

`callback_url` 省略或传 `null` 时启用同步模式：

```json
{
  "keyword": "大健康",
  "result_type": "低粉爆款",
  "time_range": "近7天",
  "input_timeout": 30,
  "detail_delay": 1,
  "limit": 3,
  "analyze_timeout": 90,
  "analyze_delay": 0,
  "callback_url": null
}
```

### 2.3 完整异步请求

`callback_url` 有值时启用异步回调模式：

```json
{
  "keyword": "大健康",
  "result_type": "低粉爆款",
  "time_range": "近7天",
  "input_timeout": 30,
  "detail_delay": 1,
  "limit": 3,
  "analyze_timeout": 90,
  "analyze_delay": 0,
  "callback_url": "https://example.com/hooks/douhot"
}
```

## 3. 同步模式

同步模式的调用顺序：

```text
HTTP 请求
  → 创建 collect 任务
  → 进入全局 FIFO
  → 获取 DouHot Cookie
  → 爬取关键词视频
  → 获取 Douyin Cookie
  → 提取口播和视频播放地址
  → 转换最终数组
  → HTTP 200 返回数组
```

完整调用示例：

```bash
curl -X POST 'http://127.0.0.1:28131/api/v1/viral-videos/collect' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "keyword":"大健康",
    "result_type":"低粉爆款",
    "time_range":"近7天",
    "input_timeout":30,
    "detail_delay":1,
    "limit":3,
    "analyze_timeout":90,
    "analyze_delay":0,
    "callback_url":null
  }'
```

同步请求会一直等待排队、爬取和解析结束，可能持续数分钟。如果前面已有 pipeline 或其他任务，还需要等待前面的 FIFO 任务完成。

部署 Nginx、网关或负载均衡器时，应将读取超时设置到足够长，否则客户端可能在服务仍正常执行任务时提前断开连接。

## 4. 异步回调模式

提供 `callback_url` 后，创建接口不会等待爬取完成，而是立即返回 HTTP `202`：

```json
{
  "task_id": "42118d44-6334-4a0c-a9a5-9a5096ab2962",
  "status": "queued",
  "created": true
}
```

调用方必须保存 `task_id`，它可用于查询、暂停和恢复任务。

任务完成后，服务向 `callback_url` 发起：

```http
POST /hooks/douhot HTTP/1.1
Content-Type: application/json
Accept: application/json
X-DouHot-Task-ID: 42118d44-6334-4a0c-a9a5-9a5096ab2962
```

回调 body 就是最终 JSON 数组，不增加 `data`、`result` 或其他包装层。

### 4.1 回调成功规则

- 任意 HTTP `2xx` 响应都视为成功。
- 回调响应可以没有 JSON body，例如 `204 No Content`。
- HTTP 重定向不会被跟随，并被视为失败。

### 4.2 回调重试

以下情况会自动重试：

- 网络连接失败。
- HTTP `429`。
- HTTP `5xx`。

最多尝试 4 次，对应等待时间为：

```text
第 1 次：立即
第 2 次：等待 2 秒
第 3 次：等待 5 秒
第 4 次：等待 10 秒
```

其他非 `2xx` 响应立即失败。所有回调尝试失败后，collect 任务进入 `failed`。

回调接收方应使用 `X-DouHot-Task-ID` 做幂等处理，避免网络重试造成重复入库。

### 4.3 失败通知

只有任务成功生成最终数组时才会发送数组回调。任务爬取失败、全部口播解析失败或回调本身最终失败时，不会再发送另一种错误对象到 `callback_url`。

调用方应使用创建接口返回的 `task_id` 查询失败原因：

```http
GET /api/v1/tasks/{task_id}
```

## 5. 最终数据数组

同步响应和异步回调使用完全相同的数据结构：

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

### 5.1 字段说明

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `type` | integer | 固定为 `0` |
| `keyword` | string | 请求提供的原始关键词 |
| `videoName` | string | 视频名称 |
| `videoUrl` | string | 抖音视频分享链接 |
| `authorName` | string | 博主名称 |
| `followerCount` | integer | 总粉丝数；无法解析或为空时为 `0` |
| `heatValue` | string | 热度值，保留原展示格式 |
| `newPlayCount` | string | 新增播放量，保留原展示格式 |
| `newLikeCount` | string | 新增点赞量，保留原展示格式 |
| `likeRate` | string | 点赞率，保留原展示格式 |
| `highPraiseComment` | string | 高赞评论 |
| `videoOral` | string | 视频口播文本 |
| `videoPlayUrl` | string | 视频提取接口返回的直接播放地址 |

`videoUrl` 和 `videoPlayUrl` 含义不同，接入方不要互换：

- `videoUrl` 用于访问抖音视频页面。
- `videoPlayUrl` 是提取接口返回的媒体播放地址。

### 5.2 数据筛选和转换

以下任一字段为空时，该行不会进入最终数组：

- `videoName`
- `videoUrl`
- `authorName`
- `videoOral`

其他规则：

- `keyword` 保留请求值，不使用可能被替换或截断的 Excel Sheet 名。
- `followerCount` 支持普通数字及“千、万、亿”等中文单位，最终始终返回整数。
- `followerCount` 无法解析时按 `0` 返回，并在任务中记录 warning。
- 没有搜索结果时正常返回或回调空数组 `[]`。
- 部分视频口播解析失败时，返回其余成功记录，任务状态可能为 `succeeded_with_warnings`。
- 已爬到视频但全部口播解析失败时，任务失败，不返回成功空数组。

## 6. 查询异步任务

请求：

```bash
curl -X GET \
  'http://127.0.0.1:28131/api/v1/tasks/42118d44-6334-4a0c-a9a5-9a5096ab2962' \
  -H 'Accept: application/json'
```

collect 任务可能出现的阶段：

| `phase` | 说明 |
| --- | --- |
| `crawl` | 正在爬取关键词视频 |
| `analyze` | 正在提取口播和播放地址 |
| `callback` | 正在发送异步结果回调 |

终态包括：

- `succeeded`
- `succeeded_with_warnings`
- `failed`

成功任务的 `result` 包含：

```json
{
  "crawl": {
    "added_count": 0,
    "skipped_count": 0,
    "sheet": "大健康",
    "stopped": false
  },
  "analyze": {
    "succeeded": 0,
    "skipped": 0,
    "failed": 0
  },
  "record_count": 0,
  "records": [],
  "artifact": {
    "path": "tasks/42118d44-6334-4a0c-a9a5-9a5096ab2962/result.xlsx",
    "row_count": 3,
    "sha256": "..."
  }
}
```

有合格记录时，`records` 是与同步响应或异步回调完全相同的最终数组。

## 7. 暂停和恢复

异步模式返回 `task_id` 后，可以调用：

```http
POST /api/v1/tasks/{task_id}/pause
POST /api/v1/tasks/{task_id}/resume
```

暂停不是立即强制终止：

- 爬取阶段会在当前视频处理完成后的安全检查点停止。
- 解析阶段会在当前口播请求结束并保存结果后停止。
- 回调阶段没有协作式中断点；已经开始回调后会继续完成当前请求及必要重试，暂停请求可能来不及生效。

同步模式不会在响应中返回 `task_id`，因此通常不使用外部暂停控制。

## 8. 错误响应

同步 HTTP 错误使用统一结构：

```json
{
  "error": {
    "code": "COLLECT_FAILED",
    "message": "所有已爬取视频的口播解析均失败",
    "details": null
  }
}
```

常见错误：

| HTTP 状态码 | `error.code` | 场景 |
| --- | --- | --- |
| `409` | `COLLECT_PAUSED` | 同步等待期间任务被暂停 |
| `422` | `VALIDATION_ERROR` | 缺少 keyword、字段越界、callback URL 无效或存在额外字段 |
| `502` | `COLLECT_FAILED` | 爬取、Cookie、口播解析或其他任务阶段失败 |
| `500` | `COLLECT_RESULT_INVALID` | 任务成功但没有生成有效最终数组 |
| `500` | `INTERNAL_ERROR` | 未预期的接口内部错误 |

异步模式已经返回 `202` 后发生的错误不会再通过创建请求返回。应查询任务状态中的：

- `status`
- `error`
- `warning_count`
- `progress.warnings`

## 9. Python 调用示例

### 9.1 同步调用

```python
import httpx

payload = {
    "keyword": "大健康",
    "result_type": "低粉爆款",
    "time_range": "近7天",
    "input_timeout": 30,
    "detail_delay": 1,
    "limit": 3,
    "analyze_timeout": 90,
    "analyze_delay": 0,
    "callback_url": None,
}

with httpx.Client(timeout=600) as client:
    response = client.post(
        "http://127.0.0.1:28131/api/v1/viral-videos/collect",
        json=payload,
    )
    response.raise_for_status()
    records = response.json()

print(f"收到 {len(records)} 条视频数据")
```

### 9.2 异步回调调用

```python
import httpx

payload = {
    "keyword": "大健康",
    "result_type": "低粉爆款",
    "time_range": "近7天",
    "input_timeout": 30,
    "detail_delay": 1,
    "limit": 3,
    "analyze_timeout": 90,
    "analyze_delay": 0,
    "callback_url": "https://example.com/hooks/douhot",
}

response = httpx.post(
    "http://127.0.0.1:28131/api/v1/viral-videos/collect",
    json=payload,
    timeout=30,
)
response.raise_for_status()
accepted = response.json()

print(accepted["task_id"])
```

## 10. 接入检查清单

- [ ] 只把 `keyword` 作为必填字段处理。
- [ ] 根据是否存在 `callback_url` 区分 `200` 和 `202`。
- [ ] 同步调用设置足够长的客户端和反向代理超时。
- [ ] 异步调用持久化保存 `task_id`。
- [ ] 回调接口接受 JSON 数组，而不是对象包装结构。
- [ ] 回调接口根据 `X-DouHot-Task-ID` 做幂等处理。
- [ ] 将 `followerCount` 按整数接收。
- [ ] 区分 `videoUrl` 和 `videoPlayUrl`。
- [ ] 正确处理成功空数组 `[]`。
- [ ] 异步任务失败时通过任务查询接口读取错误。
- [ ] 不假设该接口会自动把数据上传到榜单数据库。
