# DouHotCrawler 使用指南

DouHotCrawler 用于按关键词采集 Douhot 热榜视频，并将结果保存为 Excel；也可以为已有视频补全口播文本。

使用桌面版无需安装 Python、uv 或其他开发工具。

## 下载正确的版本

在 GitHub 的 **Actions** 页面打开一次成功的 “Package desktop application” 工作流，下载与你的电脑相符的构建产物。

| 下载包名称 | 适用设备 |
| --- | --- |
| `DouHotCrawler-windows-x86_64` | 普通 Windows 电脑，Intel 或 AMD 处理器 |
| `DouHotCrawler-windows-arm64` | Windows on ARM 电脑，例如 Snapdragon X 系列 |
| `DouHotCrawler-macos-x86_64` | Intel 芯片的 Mac |
| `DouHotCrawler-macos-arm64` | Apple 芯片的 Mac（M1、M2、M3、M4 等） |
| `DouHotCrawler-linux-x86_64` | Intel 或 AMD 处理器的 Linux 电脑 |
| `DouHotCrawler-linux-arm64` | ARM64 Linux 设备 |

不确定 Mac 芯片类型时，点击屏幕左上角 Apple 菜单 → “关于本机”：显示“芯片 Apple ……”时选择 `macos-arm64`；显示“处理器 Intel ……”时选择 `macos-x86_64`。

## 首次使用

开始前请准备稳定网络、可登录 Douhot 和抖音的个人账号，并预留足够磁盘空间供首次下载 Chromium。

1. 解压下载文件。
2. 保留整个 `DouHotCrawler` 文件夹，不要只移动其中的主程序。
3. 启动主程序：
   - Windows：双击 `DouHotCrawler.exe`。
   - macOS：双击 `DouHotCrawler`；若系统阻止打开，在 Finder 中按住 Control 点击程序，再选择“打开”。
   - Linux：在文件夹内执行 `chmod +x DouHotCrawler`，再双击或运行 `./DouHotCrawler`。
4. 程序会检查 Chromium。首次缺失时会显示下载提示，点击“是”并等待下载完成；下载完成前请保持程序打开和网络连接。
5. 在“热榜爬取”页的“浏览器准备”中确认显示“Chromium 已就绪”。
6. 点击“爬虫 Cookie 检测”的状态按钮，浏览器会打开 Douhot 登录页。完成扫码后，回到程序点击“已完成扫码，保存登录”。
7. 如需提取口播，在“口播提取”页粘贴你自己从抖音网页取得的完整 Cookie，并点击“保存 Cookie”。请勿向他人发送 Cookie。

完成以上步骤后，后续启动通常不需要再次下载 Chromium 或重复登录；登录状态失效时按相同步骤重新登录或更新 Cookie。

## 采集热榜

1. 打开“热榜爬取”。
2. 输入关键词，例如“美容”。
3. 选择榜单类型和时间范围。
4. 点击“开始爬取”。
5. 在下方“运行日志”查看进度。任务结束后，结果会保存到 Excel。

重复采集同一关键词时，已存在的视频会自动跳过，适合持续补充数据。

## 提取视频口播

1. 先完成至少一次热榜采集，确保已有结果 Excel。
2. 打开“口播提取”。
3. 如有需要，填写指定 Sheet 名称、最多处理条数或请求间隔。
4. 点击“开始提取口播”。

已写入口播的记录默认跳过；如确实要重新提取，勾选“覆盖已有口播”。

## 导出与安全停止

- 任务完成后，点击窗口顶部“下载 Excel”，选择保存位置即可导出结果。
- 需要停止时，点击“终止当前任务”。程序会完成当前记录，并保存已完成的内容后停止。
- 请在任务结束后再关闭程序或导出 Excel。

## 常见问题

### 无法下载 Chromium

检查网络连接、磁盘空间和系统代理设置，然后点击“下载 Chromium”重试。Linux 电脑还需要具备正常的图形桌面运行环境。

### 无法开始爬取

确认“浏览器准备”显示“Chromium 已就绪”，并已完成 Douhot 扫码登录。

### 无法提取口播

请重新从抖音网页复制完整 Cookie 并保存。Cookie 可能因退出登录、过期或账号状态变化而失效。

### Windows 或 macOS 提示未知开发者

这是未签名应用的系统安全提示。请确认下载来源正确后，按系统提示继续打开；不要从不可信来源下载程序。

## 隐私与账号安全

- Douhot 登录状态和抖音 Cookie 仅保存在使用者自己的电脑上。
- 不要上传、共享或发送 Cookie、登录二维码、结果 Excel 或包含个人信息的日志。
- 使用前请确认你的账号和使用方式符合相关平台的规则。
