#!/usr/bin/env python3
"""真实联调环境（本地，非演示）：独立数据目录 + 真实供应商 + 独立世界任务进程。

    python scripts/real_integration.py start            # 启动 API（默认 127.0.0.1:18763）与任务进程
    python scripts/real_integration.py status           # 运行状态：配置与数据、供应商“已配置/已验证”、任务进程、能力、前端怎么连
    python scripts/real_integration.py stop             # 停止本脚本启动的进程
    python scripts/real_integration.py restart-worker   # 只把任务进程强制结束再起一个（验证崩溃后接手、不重复结算）

- 环境标签 real-local；演示线路关闭；SQLite WAL；世界由独立任务进程推进（API 进程里不跑）；
- 供应商密钥只从 PetJourneyBackend/data/secrets/web-providers.env（git 忽略）按白名单读取，只传给子进程环境，从不打印；
- 会话密钥在数据目录里生成一次（权限尽量收紧），不打印；
- 数据目录默认 PetJourneyBackend/data/web-real-acceptance（git 忽略），不碰默认库与其他窗口的数据；
- 前端连接：cd PetJourneyWeb && PETSOUL_DEV_API_TARGET=http://127.0.0.1:18763 npx vite --mode live --port 5290。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "PetJourneyBackend"
SECRETS = BACKEND / "data" / "secrets" / "web-providers.env"
PROVIDER_KEYS = [
    "OPENAI_API_KEY", "PETJOURNEY_LLM_PROVIDER", "PETJOURNEY_OPENAI_BASE_URL", "PETJOURNEY_AGENT_MODEL",
    "AMAP_API_KEY", "GOOGLE_MAPS_API_KEY", "PETJOURNEY_MAP_TIMEOUT_SECONDS",
    "DOUBAO_API_KEY", "PETJOURNEY_DOUBAO_BASE_URL", "PETJOURNEY_IMAGE_PROVIDER", "PETJOURNEY_VOLCENGINE_IMAGE_MODEL", "PETJOURNEY_IMAGE_TIMEOUT_SECONDS",
]


def data_dir(args) -> Path:
    return Path(args.data_dir).resolve() if args.data_dir else BACKEND / "data" / "web-real-acceptance"


def build_env(args) -> dict[str, str]:
    root = data_dir(args)
    (root / "uploads").mkdir(parents=True, exist_ok=True)
    secret_file = root / "auth-secret"
    if not secret_file.exists():
        secret_file.write_text(secrets.token_hex(32), encoding="utf-8")
        try:
            os.chmod(secret_file, 0o600)
        except OSError:
            pass
    env = {**os.environ,
           "TZ": "UTC",
           "PYTHONIOENCODING": "utf-8",
           "PETJOURNEY_DB_PATH": str(root / "petjourney.sqlite3"),
           "PETJOURNEY_UPLOAD_DIR": str(root / "uploads"),
           "PETJOURNEY_WEB_PRIVATE_MEDIA_DIR": str(root / "web-private-media"),
           "PETJOURNEY_PUBLIC_BASE_URL": f"http://127.0.0.1:{args.port}",
           "PETJOURNEY_CORS_ORIGINS": "http://127.0.0.1:5290,http://127.0.0.1:5287,http://127.0.0.1:4287",
           "PETJOURNEY_PROVIDER_MODE": "mock", "PETJOURNEY_MAP_PROVIDER": "mock",  # 旧 iOS 引擎仍不调用真实供应商
           "PETJOURNEY_TRANSPORT_SCHEDULE_PROVIDER": "mock", "PETJOURNEY_TRAVEL_GUIDE_RESEARCH_PROVIDER": "mock",
           "PETJOURNEY_SCHEDULER_ENABLED": "false",
           "PETJOURNEY_APPLE_AUTH_MODE": "live",
           "PETJOURNEY_AUTH_SECRET": secret_file.read_text(encoding="utf-8").strip(),
           "PETJOURNEY_WEB_COOKIE_SECURE": "false",
           "PETJOURNEY_LEGACY_API_POLICY": "closed",
           "PETJOURNEY_WEB_ENVIRONMENT": "real-local",
           "PETJOURNEY_WEB_DEMO_CATALOG": "",
           "PETJOURNEY_SQLITE_WAL": "1",
           "PETJOURNEY_WEB_WORLD_RUNNER": "worker",
           "PETJOURNEY_WEB_WORLD_TICK_SECONDS": str(args.tick),
           "PETJOURNEY_WEB_PROVIDERS": "0"}
    for key in PROVIDER_KEYS + ["OPENAI_API_KEY", "IMAGE_API_KEY", "OPENAI_IMAGE_API_KEY", "PETJOURNEY_IMAGE_API_KEY"]:
        env.pop(key, None)  # 不继承外部环境里的密钥，只用下面白名单文件里的
    if args.providers:
        if not SECRETS.exists():
            raise SystemExit(f"找不到供应商配置文件：{SECRETS.relative_to(ROOT)}")
        loaded = []
        for line in SECRETS.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$", line)
            if m and m.group(1) in PROVIDER_KEYS and m.group(2):
                env[m.group(1)] = m.group(2)
                loaded.append(m.group(1))
        env["PETJOURNEY_WEB_PROVIDERS"] = "1"
        print(f"[real] 真实供应商已开启（仅服务端）：{', '.join(k for k in loaded if 'KEY' not in k)}；密钥 {sum('KEY' in k for k in loaded)} 个（不显示）")
    return env


def start(args) -> None:
    root = data_dir(args)
    run = root / "run.json"
    if run.exists():
        raise SystemExit(f"已经有一套在运行（{run.relative_to(ROOT)}）；先 stop。")
    env = build_env(args)
    python = sys.executable
    api_log = open(root / "api.log", "ab")
    worker_log = open(root / "worker.log", "ab")
    api = subprocess.Popen([python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.port)], cwd=BACKEND, env=env,
                           stdout=api_log, stderr=subprocess.STDOUT)
    for _ in range(60):  # 等 API 起来（迁移在 API 启动时应用），再起任务进程，避免两边同时迁移
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/v1/web/meta", timeout=2)
            break
        except Exception:  # noqa: BLE001
            time.sleep(1)
    worker = subprocess.Popen([python, "-m", "app.web_worker"], cwd=BACKEND, env=env, stdout=worker_log, stderr=subprocess.STDOUT)
    run.write_text(json.dumps({"api_pid": api.pid, "worker_pid": worker.pid, "port": args.port, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}),
                   encoding="utf-8")
    print(f"[real] API  http://127.0.0.1:{args.port}  PID {api.pid}；任务进程 PID {worker.pid}；数据 {root.relative_to(ROOT)}")
    print(f"[real] 前端：cd PetJourneyWeb && PETSOUL_DEV_API_TARGET=http://127.0.0.1:{args.port} npx vite --mode live --port 5290")


def status(args) -> None:
    port = args.port
    run = data_dir(args) / "run.json"
    if run.exists():
        port = json.loads(run.read_text(encoding="utf-8")).get("port", port)
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/web/ops/status", timeout=5) as response:
        body = json.loads(response.read().decode("utf-8"))
    print(f"环境 {body['environment']}  后端 {body['backend_version']}  数据库 {body['database']}  WAL {body['sqlite_wal']}  迁移 {body['applied_migrations']}（最后 {body['last_migration']}）")
    for p in body["providers"]:
        print(f"  供应商 {p['label']:<14} {p['state']:<15} 今天 {p['calls_today']}/{p['daily_cap']}  最近成功 {p['last_success_at'] or '-'}")
    w = body["world"]
    print(f"  世界任务 runner={w['runner']} 本进程在跑={w['running_here']} 租约有效={w['lease_alive']} 持有={w['lease_holder_role']}:{w['lease_pid']} "
          f"最近一轮 {w['last_tick_at']} 成功 {w['last_ok_at']} 共 {w['ticks']} 轮 错误 {w['last_error'] or '-'}")
    unavailable = [c["key"] for c in body["capabilities"] if c["status"] != "available"]
    print(f"  能力：{len(body['capabilities'])} 项，其中未就绪 {len(unavailable)} 项：{', '.join(unavailable)}")
    print(f"  前端：{body['frontend']['note']}")


def stop(args) -> None:
    run = data_dir(args) / "run.json"
    if not run.exists():
        print("[real] 没有记录在运行的进程。")
        return
    info = json.loads(run.read_text(encoding="utf-8"))
    for key in ("worker_pid", "api_pid"):  # 先停任务进程（释放租约），再停 API
        pid = info.get(key)
        try:
            os.kill(pid, signal.SIGTERM if os.name != "nt" else signal.SIGINT)
        except (OSError, TypeError):
            pass
        time.sleep(2)
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    run.unlink()
    print(f"[real] 已停止 API PID {info.get('api_pid')} 与任务进程 PID {info.get('worker_pid')}。")


def restart_worker(args) -> None:
    """只重启世界任务进程（强制结束，不释放租约；新进程在租约过期后接手——模拟任务进程崩溃）。"""
    root = data_dir(args)
    run = root / "run.json"
    if not run.exists():
        raise SystemExit("没有在运行的联调环境。")
    info = json.loads(run.read_text(encoding="utf-8"))
    old = info.get("worker_pid")
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(old), "/T", "/F"], capture_output=True)
    else:
        try:
            os.kill(old, signal.SIGKILL)
        except OSError:
            pass
    env = build_env(args)
    worker = subprocess.Popen([sys.executable, "-m", "app.web_worker"], cwd=BACKEND, env=env, stdout=open(root / "worker.log", "ab"), stderr=subprocess.STDOUT)
    info["worker_pid"] = worker.pid
    run.write_text(json.dumps(info), encoding="utf-8")
    print(f"[real] 任务进程 {old} 已强制结束；新任务进程 PID {worker.pid}（租约过期后接手）。")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("start", "status", "stop", "restart-worker"))
    parser.add_argument("--port", type=int, default=18763)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--tick", type=float, default=30.0, help="世界任务间隔秒数")
    parser.add_argument("--no-providers", dest="providers", action="store_false", help="不开真实供应商（只验证流程）")
    args = parser.parse_args()
    {"start": start, "status": status, "stop": stop, "restart-worker": restart_worker}[args.action](args)


if __name__ == "__main__":
    main()
