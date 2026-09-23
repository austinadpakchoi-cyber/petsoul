"""独立验收（工作包 Q）合同回归的隔离与观测工具。非测试模块（不以 test 开头），discover 不收集。

- isolate()：在导入 app 之前调用。把模块级 create_app() 会用到的库、上传与私有媒体目录指到 Q 自己的临时根，
  预先占住供应商密钥类环境变量（置空），这样即使仓库里出现 .env 也不会被 load_settings() 读进来；临时文件不落系统临时目录；
- GUARD：审计钩子禁网。只在 `with GUARD.active():` 里生效（放进默认 discover 时不影响别的测试）；
  asyncio 在 Windows 上用回环 socketpair 做自唤醒，这一种连接放行，其余连接/解析/HTTP 一律拦下并计数；
- HangingChat：模型替身，被调用后一直挂起到 release()，最后抛 ChatUnavailable（不返回任何文字）；
- db_snapshot / db_diff：按表比较行数与内容摘要（只读打开隔离库）；
- run_child()：在子进程里执行一段代码（同样隔离、禁网、不写字节码），用来模拟“进程被杀”。

所有路径都在 PetJourneyBackend/data/reviews/q-4d18-20260922/ 之下（git 忽略），不碰 18761/18763 与任何业务库。
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
TESTS = BACKEND / "tests"
Q_ROOT = BACKEND / "data" / "reviews" / "q-4d18-20260922"
PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"
LEVEL_UNIT = "单元（真实类＋隔离 SQLite；非 HTTP）"
LEVEL_INTEGRATION = "集成（隔离 SQLite＋进程内 TestClient＋禁网替身；非真实供应商、非线上）"
LEVEL_PROCESS = "集成（隔离 SQLite＋两个真实进程；非真实供应商、非线上）"
# 供应商密钥与会改变行为的开关：预先占位（load_env_file 不覆盖已有键），置空即“未配置”
_PINNED_ENV = ("OPENAI_API_KEY", "AMAP_API_KEY", "GOOGLE_MAPS_API_KEY", "DOUBAO_API_KEY", "PETJOURNEY_IMAGE_API_KEY", "IMAGE_API_KEY",
               "OPENAI_IMAGE_API_KEY", "PETJOURNEY_ADMIN_TOKEN", "PETJOURNEY_POSTGRES_DSN", "PETJOURNEY_APNS_PRIVATE_KEY_PATH")
_BLOCKED_EVENTS = {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.sendto",
                   "socket.sendmsg", "http.client.connect", "urllib.Request"}


def isolate(run_root: Path) -> dict[str, Any]:
    """把本进程的数据目录、临时目录与供应商配置隔离到 run_root；必须在第一次 import app 之前调用才对模块级 app 生效。"""
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "tmp").mkdir(exist_ok=True)
    tempfile.tempdir = str(run_root / "tmp")
    os.environ.update({
        "PETJOURNEY_DB_PATH": str(run_root / "module-app.sqlite3"), "PETJOURNEY_UPLOAD_DIR": str(run_root / "module-uploads"),
        "PETJOURNEY_WEB_PRIVATE_MEDIA_DIR": str(run_root / "module-private"), "PETJOURNEY_SCHEDULER_ENABLED": "false",
        "PETJOURNEY_WEB_PROVIDERS": "0", "PETJOURNEY_WEB_WORLD_RUNNER": "off", "PETJOURNEY_LLM_PROVIDER": "mock",
        "PETJOURNEY_PROVIDER_MODE": "mock", "PETJOURNEY_MAP_PROVIDER": "mock", "PETJOURNEY_INTENT_LAYER_MODE": "off", "TZ": "UTC",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    for name in _PINNED_ENV:
        os.environ[name] = ""
    sys.dont_write_bytecode = True
    return {"run_root": str(run_root), "env_files_present": [n for n in (".env", ".env.features") if (BACKEND / n).exists()],
            "pinned_env": list(_PINNED_ENV), "app_already_imported": "app.main" in sys.modules}


class NetworkGuard:
    """审计钩子：active() 期间拦下一切对外连接与域名解析（回环 socketpair 除外），并记录尝试次数。钩子装上后不能卸载，未激活时不做任何事。"""

    def __init__(self) -> None:
        self.attempts: list[str] = []
        self._installed = False
        self._depth = 0
        self._local = threading.local()

    def install(self) -> "NetworkGuard":
        if self._installed:
            return self
        original = socket.socketpair

        def socketpair(*args, **kwargs):  # asyncio 的自唤醒管道：Windows 上用回环连接实现，放行
            self._local.pairing = True
            try:
                return original(*args, **kwargs)
            finally:
                self._local.pairing = False

        socket.socketpair = socketpair
        sys.addaudithook(self._hook)
        self._installed = True
        return self

    def _hook(self, event: str, args: tuple) -> None:
        if self._depth <= 0 or event not in _BLOCKED_EVENTS:
            return
        if event == "socket.connect" and getattr(self._local, "pairing", False):
            return
        target = args[1] if event == "socket.connect" and len(args) > 1 else (args[0] if args else None)
        self.attempts.append(f"{event}:{str(target)[:80]}")
        raise RuntimeError(f"Q 合同回归禁网：拦下 {event}")

    @contextlib.contextmanager
    def active(self):
        self.install()
        self._depth += 1
        try:
            yield self
        finally:
            self._depth -= 1


GUARD = NetworkGuard()


@dataclass
class ContractResult:
    contract_id: str
    title: str
    acceptance: str  # 世界运行方案 §18 的验收编号
    level: str
    owner: str  # 缺口应交给哪个包
    status: str  # PASS / FAIL / BLOCKED
    expected: Any
    observed: Any
    repro: list[str]
    sources: dict[str, str] = field(default_factory=dict)  # 被测源文件 SHA-256 前 16 位：结论只对这些版本有效
    network_attempts: int = 0

    def as_message(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=1, default=str)


RESULTS: list[ContractResult] = []


def source_digests(*relative: str) -> dict[str, str]:
    digests = {}
    for rel in relative:
        path = BACKEND / rel
        digests[rel] = hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else "missing"
    return digests


class HangingChat:
    """模型替身：被调用时记下次数并挂起，直到 release() 或超时。reply 为空时随后抛 ChatUnavailable（模型挂住/超时）；
    给了 reply 则在放行后返回这段文字（模型在别的事情已经发生之后才答完）。"""

    available = True
    provider_label = "Q 挂起的测试模型"

    def __init__(self, hold_seconds: float = 20.0, reply: str | None = None) -> None:
        self.entered = threading.Event()
        self.released = threading.Event()
        self.calls = 0
        self.hold_seconds = hold_seconds
        self.reply = reply

    def complete(self, messages, *, max_tokens=200, temperature=0.7, json_mode=False):  # noqa: ARG002 - 与 WebChat 同签名
        from app.web_providers import ChatResult, ChatUnavailable

        self.calls += 1
        self.entered.set()
        self.released.wait(self.hold_seconds)
        if self.reply is None:
            raise ChatUnavailable("q-hanging-model")
        return ChatResult(text=self.reply, requested_model="q-hanging", effective_model="q-hanging", latency_ms=1)

    def release(self) -> None:
        self.released.set()


def db_snapshot(db_path: Path, skip: frozenset[str] = frozenset()) -> dict[str, tuple[int, str]]:
    """{表名: (行数, 内容摘要)}；只读打开，不改库。"""
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        snapshot = {}
        for table in tables:
            if table in skip:
                continue
            rows = sorted(repr(row) for row in conn.execute(f'SELECT * FROM "{table}"'))
            snapshot[table] = (len(rows), hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()[:16])
        return snapshot
    finally:
        conn.close()


def db_diff(before: dict[str, tuple[int, str]], after: dict[str, tuple[int, str]]) -> dict[str, dict[str, int]]:
    """有变化的表：{表名: {"rows_before": n, "rows_after": m}}（内容变了但行数不变也列出）。"""
    changed = {}
    for table in sorted(set(before) | set(after)):
        if before.get(table) != after.get(table):
            changed[table] = {"rows_before": (before.get(table) or (0, ""))[0], "rows_after": (after.get(table) or (0, ""))[0]}
    return changed


def run_child(code: str, run_root: Path, timeout: float = 120.0) -> subprocess.CompletedProcess:
    """子进程里执行 code：先隔离、禁网，再执行。子进程可以 os._exit() 模拟被杀。输出只含 code 自己打印的内容。"""
    bootstrap = (
        "import sys\n"
        f"sys.path[:0] = [{str(BACKEND)!r}, {str(TESTS)!r}]\n"
        "from pathlib import Path\n"
        "import runtime_contract_harness as h\n"
        f"h.isolate(Path({str(run_root)!r}))\n"
        "h.GUARD.install()._depth = 1\n"
    )
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8", "TZ": "UTC"}
    return subprocess.run([sys.executable, "-B", "-c", bootstrap + code], capture_output=True, text=True, encoding="utf-8",
                          timeout=timeout, env=env, cwd=str(BACKEND))
