# Douhot 热榜爬虫（MVP）

基于 Crawl4AI 和已登录的 Douhot 浏览器 Profile，按关键词检索抖音热榜视频，采集榜单指标、视频链接和高赞评论，并增量写入一个 Excel 结果库。

当前版本是第一阶段 MVP：已跑通搜索、筛选、分页采集、详情页信息提取、评论采集和 Excel 增量入库。

## 功能

- 按关键词搜索 Douhot 视频榜。
- 选择类型筛选和时间范围筛选。
- 采集视频名称、博主、粉丝数、热度、播放/点赞增量、点赞率与前四条高赞评论。
- 通过详情页 `video_id` 生成标准抖音视频链接。
- 结果保存到 `result/result.xlsx`，每个关键词对应一个 Sheet。
- 使用“视频名称 + 博主名称”增量去重；已存在的视频会在列表页被跳过，不再打开详情页。

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- 已安装 Chromium（Crawl4AI 会使用受管浏览器）
- 可登录的 Douhot / 抖音账号

安装依赖：

```bash
uv sync
```

## 首次使用：创建登录 Profile

爬虫复用本地浏览器 Profile：`~/.crawl4ai/profiles/douhot`。首次运行前执行：

```bash
uv run crwl profiles
```

在打开的浏览器中登录 Douhot，完成后按 `q` 保存并退出。之后正常运行无需重复登录；若登录状态失效，重新创建或更新该 Profile。

图形界面会自动检查本地 Profile 中的 Douhot 登录 Cookie，并显示有效、即将过期、已过期或缺失状态。该状态依据本地 Cookie 的到期时间，无法识别服务端主动吊销但尚未到期的 Cookie。

图形界面将两类凭据分别显示在对应页签：

- “爬虫Cookie检测”检查 Crawl4AI 的 Douhot Profile；失效后点击状态按钮打开扫码登录。
- “口播Cookie检测”检查 `cookie.config` 中 `www.douyin.com` 的 Cookie；过期后在输入框粘贴新 Cookie 并保存。该检查从 `sid_guard` 的本地有效期判断，无法解析有效期时会标记为“已配置”，由实际口播提取最终验证。

## 运行

最小命令：

```bash
uv run douhot-crawl "大健康"
```

指定筛选条件：

```bash
uv run douhot-crawl "大健康" \
  --result-type "低粉爆款" \
  --time-range "近1天"
```

可用参数：

| 参数 | 说明 |
| --- | --- |
| `keyword` | 必填，搜索关键词。 |
| `--result-type` | 类型筛选；默认 `低粉爆款`。 |
| `--time-range` | `近1小时`、`近1天`、`近3天` 或 `近7天`；默认 `近7天`。 |
| `--input-timeout` | 等待搜索框渲染的秒数；默认 `30`。 |
| `--detail-delay` | 每条新视频详情采集后的基础等待秒数；默认 `1`，会随机浮动 ±`0.2` 秒。 |
| `--headless` | 无头运行；首次排错时建议不使用。 |

### 安全退出

运行期间，在启动命令的终端输入 `q` 并按回车。程序会完成当前页采集、写入该页 Excel 数据并关闭浏览器，然后正常退出；不需要使用 `Ctrl+C`。

## 输出与增量规则

输出文件固定为：

```text
result/result.xlsx
```

每个关键词有独立 Sheet。表头如下：

```text
序号、类型、爬取到的时间、时间类型、视频名称、视频的url、博主名称、
总粉丝数、热度值、新增播放量、新增点赞量、点赞率、高赞评论
```

同一关键词再次运行时：

1. 先读取该 Sheet 中已有的“视频名称 + 博主名称”。
2. 列表页命中已有组合时，跳过详情页，不再重复请求。
3. 每完成一页采集，就将该页新视频追加到 Sheet 末尾。

因此手动暂停或异常退出时，已经完成的页面不会丢失；最多丢失正在采集、尚未完成写入的当前页。

这个去重键适合高效增量采集；极少数情况下，同一博主发布同名不同视频可能被视为重复。

## 项目结构

```text
.
├── douhot_crawler/
│   ├── __main__.py            # douhot-crawl 命令入口
│   ├── analyzer.py            # douhot-analyze 命令入口与口播写入
│   ├── gui.py                 # douhot-gui 图形界面
│   ├── login_cli.py           # douhot-login 命令入口
│   ├── app.py                 # 运行编排：浏览器、钩子、入库
│   ├── cli.py                 # 命令行参数
│   ├── config.py              # URL、默认值和输出字段
│   ├── cookie_status.py        # Crawl4AI Profile Cookie 检测
│   ├── transcript_cookie_status.py  # 口播 Cookie 检测与安全保存
│   ├── login.py                # Douhot 扫码登录流程
│   ├── models.py              # RunOptions、视频记录与去重键
│   ├── page_actions.py        # 搜索框、搜索提交、类型/时间筛选
│   ├── collector.py           # 列表解析、详情页采集、分页
│   ├── comments.py            # 评论分析页与高赞评论提取
│   └── storage.py             # Excel 表头迁移、增量去重与写入
├── scripts/
│   └── gui.sh                 # GUI shell 启动器
├── tests/
│   └── test_cookie_status.py  # Cookie 检测与保存测试
├── result/
│   └── result.xlsx            # 运行后生成的总结果库
├── cookie.config              # 口播提取的抖音 Cookie（运行时文件）
├── pyproject.toml
└── uv.lock
```

## 当前边界与下一步

- 新视频详情采集默认间隔为 `1 ± 0.2` 秒；如需更保守，可通过 `--detail-delay` 增大基础等待时间。
- 视频记录按页写入后立即释放，详情页弹窗也会逐条关闭，避免长任务累积页面对象和记录列表。

## 第二阶段：视频口播提取

`douhot-analyze` 会读取 `result/result.xlsx` 的“视频的url”列，使用 `cookie.config` 调用视频提取接口，并将接口返回的 `transcript` 写入“视频口播”列。已有口播的行默认跳过，支持断点续跑。

```bash
uv run douhot-analyze
```

先小批量验证一个 Sheet：

```bash
uv run douhot-analyze --sheet "美容" --limit 1
```

## 图形界面

图形界面基于 PySide6 与 QFluentWidgets，可从一个窗口启动热榜爬取或口播提取，并查看实时日志：

```bash
uv run douhot-gui
```

顶部“下载 Excel”可将 `result/result.xlsx` 导出到自选位置；为保证文件完整，请在任务结束后使用。

在 KDE/Wayland 下，界面使用 Qt 原生 Wayland text-input 协议，由 KWin 转交给 Fcitx；启动时会忽略全局 `QT_IM_MODULE`，避免 PySide6 与系统 Fcitx Qt 插件的 ABI 不兼容。不再依赖 Tk/XIM。

界面中的“终止当前任务”会请求安全停止：爬虫完成正在处理的记录后，会将本页已采集数据写入 Excel 再退出；口播提取已按条写入。尚未取得详情的当前视频会在下次运行时重新处理。
- 页面选择器依赖 Douhot 当前页面结构；若页面改版，优先检查 `page_actions.py` 和 `collector.py`。
- 当前为单进程运行，适合先稳定采集和沉淀数据；并发、任务队列、断点续跑可放在下一阶段实现。
