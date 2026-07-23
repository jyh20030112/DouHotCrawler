"""不依赖 Tk 字体的本地浏览器图形界面。"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent


PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Douhot 数据工作台</title><style>
:root{--bg:#0b1220;--surface:#111c2e;--card:#16243a;--line:#2b3b55;--text:#f1f5f9;--muted:#94a3b8;--blue:#38bdf8;--danger:#fb7185}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif}main{max-width:980px;margin:auto;padding:28px 20px}.head,.card,.status{background:var(--card);border:1px solid var(--line);border-radius:14px}.head{display:flex;align-items:center;padding:22px;margin-bottom:18px}.brand{width:42px;height:42px;display:grid;place-items:center;background:var(--blue);color:#062136;font-weight:800;border-radius:10px;margin-right:14px}.head h1{font-size:20px;margin:0}.head p{color:var(--muted);font-size:13px;margin:5px 0 0}.tag{margin-left:auto;color:var(--blue);background:#13324a;padding:7px 10px;font-size:12px;border-radius:7px}.tabs{display:flex;gap:8px;margin-bottom:14px}.tab,button{font:inherit;border:0;cursor:pointer;border-radius:8px}.tab{padding:10px 16px;background:var(--surface);color:var(--muted)}.tab.on{background:var(--card);color:var(--blue)}.card{padding:24px}.card h2{margin:0;font-size:17px}.hint{margin:6px 0 18px;color:var(--muted);font-size:13px}.form{display:grid;grid-template-columns:190px 1fr;gap:12px;align-items:center}label{color:var(--muted);font-size:14px}input,select{width:100%;padding:10px 12px;color:var(--text);background:#0d182a;border:1px solid var(--line);border-radius:8px;font:inherit}input[type=checkbox]{width:auto;accent-color:var(--blue)}.wide{grid-column:2}.primary{margin-top:10px;padding:11px 17px;background:var(--blue);color:#062136;font-weight:700}.status{margin:16px 0;padding:13px 16px;display:flex;align-items:center;gap:9px;color:var(--muted)}.dot{color:var(--blue)}.stop{margin-left:auto;padding:8px 12px;background:#3a1b2a;color:#fda4af}.log-title{font-size:15px;margin:0 0 8px}.log{height:235px;overflow:auto;white-space:pre-wrap;background:#08111f;border:1px solid var(--line);border-radius:12px;padding:14px;color:#c7d2fe;font:13px/1.5 "Maple Mono NF CN","Noto Sans Mono CJK SC",monospace}.hidden{display:none}@media(max-width:620px){main{padding:16px}.tag{display:none}.form{grid-template-columns:1fr}.wide{grid-column:1}.head{padding:17px}}
</style></head><body><main><section class="head"><div class="brand">D</div><div><h1>Douhot 数据工作台</h1><p>采集热榜、补全口播，并将结果持续沉淀到 Excel</p></div><span class="tag">MVP · LOCAL</span></section>
<nav class="tabs"><button class="tab on" data-tab="crawl">热榜爬取</button><button class="tab" data-tab="analyze">口播提取</button></nav>
<section id="crawl" class="card panel"><h2>创建热榜采集任务</h2><p class="hint">每页数据会即时保存到结果库，适合长时间稳定运行。</p><div class="form"><label>关键词</label><input id="keyword" placeholder="例如：美容"><label>类型</label><select id="resultType"><option>低粉爆款</option><option>视频总榜</option><option>高完播率</option><option>高涨粉率</option><option>高点赞率</option></select><label>时间范围</label><select id="timeRange"><option>近1小时</option><option>近1天</option><option>近3天</option><option selected>近7天</option></select><label>搜索框超时（秒）</label><input id="inputTimeout" value="30"><label>详情页间隔（秒）</label><input id="detailDelay" value="1"><label></label><label><input id="headless" type="checkbox"> 无头模式</label><span></span><button class="primary" onclick="start('crawl')">开始爬取</button></div></section>
<section id="analyze" class="card panel hidden"><h2>补全视频口播</h2><p class="hint">默认跳过已提取记录，可安全分批处理和续跑。</p><div class="form"><label>Sheet（可选，逗号分隔）</label><input id="sheets" placeholder="例如：美容, 大健康"><label>最多处理条数（可选）</label><input id="limit"><label>单条超时（秒）</label><input id="timeout" value="90"><label>请求间隔（秒）</label><input id="delay" value="0"><label></label><label><input id="overwrite" type="checkbox"> 覆盖已有口播</label><span></span><button class="primary" onclick="start('analyze')">开始提取口播</button></div></section>
<section class="status"><span id="dot" class="dot">●</span><span id="status">就绪 · 等待开始</span><button class="stop" onclick="stopTask()">终止当前任务</button></section><h3 class="log-title">运行日志</h3><div id="log" class="log"></div></main><script>
const $=id=>document.getElementById(id);let task='';document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));document.querySelectorAll('.panel').forEach(x=>x.classList.add('hidden'));b.classList.add('on');$(b.dataset.tab).classList.remove('hidden')});
async function api(path,body){let r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});let data=await r.json();if(!r.ok)alert(data.error||'操作失败');return data}
async function start(kind){if(kind==='crawl'&&!$('keyword').value.trim()){alert('请输入要爬取的关键词。');return}let body=kind==='crawl'?{task:kind,keyword:$('keyword').value.trim(),result_type:$('resultType').value,time_range:$('timeRange').value,input_timeout:$('inputTimeout').value.trim(),detail_delay:$('detailDelay').value.trim(),headless:$('headless').checked}:{task:kind,sheets:$('sheets').value,limit:$('limit').value.trim(),timeout:$('timeout').value.trim(),delay:$('delay').value.trim(),overwrite:$('overwrite').checked};await api('/api/start',body)}async function stopTask(){if(confirm('将完成正在处理的记录，并将本页已采集数据写入 Excel 后退出。'))await api('/api/stop')}
async function refresh(){let s=await fetch('/api/state').then(r=>r.json());$('status').textContent=s.status;$('dot').style.color=s.running?'#38bdf8':s.error?'#fb7185':'#34d399';$('log').textContent=s.logs.join('');$('log').scrollTop=$('log').scrollHeight}setInterval(refresh,500);refresh();
</script></body></html>"""


class Dashboard:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.process: subprocess.Popen[str] | None = None
        self.status = "就绪 · 等待开始"
        self.logs: list[str] = []
        self.error = False

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            running = self.process is not None and self.process.poll() is None
            return {"status": self.status, "logs": self.logs[-1200:], "running": running, "error": self.error}

    def append(self, text: str) -> None:
        with self.lock:
            self.logs.append(text)
            if len(self.logs) > 1600:
                del self.logs[:400]

    def start(self, data: dict[str, Any]) -> None:
        with self.lock:
            if self.process and self.process.poll() is None:
                raise ValueError("已有任务正在运行，请先等待或终止。")
        task = data.get("task")
        if task == "crawl":
            keyword = str(data.get("keyword", "")).strip()
            if not keyword:
                raise ValueError("请输入要爬取的关键词。")
            command = [sys.executable, "-u", "crawler.py", keyword, "--result-type", str(data.get("result_type", "低粉爆款")), "--time-range", str(data.get("time_range", "近7天")), "--input-timeout", str(data.get("input_timeout", "30")), "--detail-delay", str(data.get("detail_delay", "1"))]
            if data.get("headless"):
                command.append("--headless")
            task_name = "热榜爬取"
        elif task == "analyze":
            command = [sys.executable, "-u", "douhot_analyze.py", "--timeout", str(data.get("timeout", "90")), "--delay", str(data.get("delay", "0"))]
            for sheet in str(data.get("sheets", "")).split(","):
                if sheet.strip():
                    command.extend(("--sheet", sheet.strip()))
            if str(data.get("limit", "")).strip():
                command.extend(("--limit", str(data["limit"]).strip()))
            if data.get("overwrite"):
                command.append("--overwrite")
            task_name = "口播提取"
        else:
            raise ValueError("未知任务类型。")
        self.append("\n$ " + " ".join(command) + "\n")
        with self.lock:
            self.status, self.error = f"{task_name}运行中", False
            self.process = subprocess.Popen(command, cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", bufsize=1)
            process = self.process
        threading.Thread(target=self._read_output, args=(process,), daemon=True).start()

    def _read_output(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            self.append(line)
        code = process.wait()
        with self.lock:
            if self.process is process:
                self.process = None
                self.status, self.error = ("任务完成", False) if code == 0 else (f"任务结束（{code}）", True)

    def stop(self) -> None:
        with self.lock:
            if not self.process or self.process.poll() is not None:
                return
            self.process.terminate()
            self.status, self.error = "正在安全停止任务…", True
        self.append("\n已请求安全停止：将写入当前页已完成的数据。\n")


def make_handler(dashboard: Dashboard) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _send(self, body: bytes, content_type: str, status: int = HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/":
                self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/state":
                self._send(json.dumps(dashboard.snapshot(), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            else:
                self._send(b'{"error":"not found"}', "application/json", HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            try:
                size = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(size) or b"{}")
                if self.path == "/api/start":
                    dashboard.start(data)
                elif self.path == "/api/stop":
                    dashboard.stop()
                else:
                    raise ValueError("请求地址不存在。")
            except (ValueError, json.JSONDecodeError) as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(body, "application/json; charset=utf-8", HTTPStatus.BAD_REQUEST)
                return
            self._send(b'{"ok":true}', "application/json")

    return Handler


def main() -> None:
    dashboard = Dashboard()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(dashboard))
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Tk 无法渲染中文，已启用本地浏览器界面：{url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已关闭本地界面服务。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
