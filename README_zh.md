# DouHotCrawler 使用指南

DouHotCrawler 用于按关键词采集 Douhot 热榜视频，并将结果保存为 Excel；也可以为已有视频补全口播文本。

使用桌面版无需安装 Python、uv 或其他开发工具。

## 系统要求

- **浏览器**：系统需安装 **Google Chrome** 或 **Microsoft Edge**

请选择与操作系统和 CPU 架构对应的安装包：

| 安装包 | 适用设备 |
| --- | --- |
| `DouHotCrawler-windows-x86_64.zip` | Windows 10 及以上，Intel / AMD x86_64 处理器 |
| `DouHotCrawler-macos-arm64.zip` | Apple Silicon Mac（M1 / M2 / M3 / M4） |
| `DouHotCrawler-Linux-x86_64.zip` | x86_64 Linux 桌面系统；构建环境为 Ubuntu 24.04 |

- 暂未提供 Windows ARM 和 Intel Mac 安装包。
- 未检测到 Chrome 或 Edge 时，可在程序内下载 Chromium。

## 下载与安装

正式版本请在仓库的 **Releases** 页面下载对应 zip 包；测试中的构建可在 GitHub **Actions** 的成功 "Package desktop application" 工作流中下载。

1. 解压下载的 zip 文件。
2. 保留解压后的全部文件，不要单独移动主程序。
3. 按系统启动：

   | 系统 | 启动方式 |
   | --- | --- |
   | Windows | 双击 `DouHotCrawler/DouHotCrawler.exe`。不要将 `.exe` 移出该文件夹。 |
   | macOS（Apple Silicon） | 双击 `DouHotCrawler.app`。若系统阻止打开未签名应用，请按住 Control 点击应用，选择“打开”并确认。 |
   | Linux x86_64 | 在解压目录执行一次 `chmod +x DouHotCrawler/DouHotCrawler`，随后执行 `./DouHotCrawler/DouHotCrawler`。 |

## 首次使用

开始前请准备稳定网络、可登录 Douhot 和抖音的个人账号。

1. 启动程序后，界面会自动检测系统 Chrome / Edge 是否可用。
2. 若未检测到 Chrome / Edge，"浏览器准备"卡片会显示"下载浏览器"，点击即可下载 Chromium。下载过程中请保持网络连接。
3. 确认"浏览器准备"显示"浏览器已就绪"。
4. 点击"爬虫 Cookie 检测"的状态按钮，浏览器会打开 Douhot 登录页。完成扫码后，点击"已完成扫码，保存登录"。
5. 如需提取口播，在"口播提取"页粘贴从抖音网页取得的完整 Cookie，并点击"保存口播 Cookie 并检测"。请勿向他人发送 Cookie。

完成以上步骤后，后续启动通常不需要再次下载浏览器或重复登录；登录状态失效时按相同步骤重新操作。

## 采集热榜

1. 打开"热榜爬取"页。
2. 输入关键词，例如"美容"。
3. 选择榜单类型和时间范围。
4. 点击"开始爬取"。
5. 在下方"运行日志"查看进度。任务结束后，结果保存到 Excel。

重复采集同一关键词时，已存在的视频会自动跳过，适合持续补充数据。

## 提取视频口播

开始前需配置私有口播提取服务。在本地创建 `.env` 文件并填写：

```bash
EXTRACT_API_URL=http://your-api-host:28600/api/v1/videos/extract
```

Windows / Linux 桌面版将 `.env` 放在主程序旁；macOS 将 `.env` 放在 `DouHotCrawler.app` 旁。源码运行时可将 `.env.example` 复制为项目根目录下的 `.env`。`.env` 不会被 Git 跟踪，严禁提交或分享；已设置的系统环境变量优先于 `.env`。

1. 先完成至少一次热榜采集，确保已有结果 Excel。
2. 打开"口播提取"页。
3. 如有需要，填写指定 Sheet 名称、最多处理条数或请求间隔。
4. 点击"开始提取口播"。

已写入口播的记录默认跳过；如确实要重新提取，勾选"覆盖已有口播"。

## 导出与停止

- 任务完成后，点击窗口顶部"下载 Excel"，选择保存位置即可导出结果。
- 需要停止时，点击"终止当前任务"。程序会完成当前记录，保存已完成的内容后停止。
- 请在任务结束后再关闭程序或导出 Excel。

## 常见问题

### 未检测到 Chrome / Edge

请确保已安装 Google Chrome 或 Microsoft Edge。如果已安装但仍未检测到，可以点击"浏览器准备"中的按钮手动下载 Chromium。

### 无法下载 Chromium

检查网络连接、磁盘空间和系统代理设置，然后重试。

### 无法开始爬取

确认"浏览器准备"显示"浏览器已就绪"，并已完成 Douhot 扫码登录。

### 无法提取口播

请重新从抖音网页复制完整 Cookie 并保存。Cookie 可能因退出登录、过期或账号状态变化而失效。

### Windows 或 macOS 阻止打开应用

这是未签名应用的系统安全提示。仅在确认 zip 来自本仓库 Release 或 Actions 构建产物后继续。macOS 可按住 Control 点击应用，选择“打开”后确认；不要从不可信来源下载程序。

## 隐私与账号安全

- Douhot 登录状态和抖音 Cookie 仅保存在使用者自己的电脑上。
- 不要上传、共享或发送 Cookie、登录二维码、结果 Excel 或包含个人信息的日志。
- 使用前请确认你的账号和使用方式符合相关平台的规则。
