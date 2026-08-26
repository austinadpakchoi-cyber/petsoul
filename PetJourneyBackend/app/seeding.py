"""演示素材播种（架构审计 P1-3 从 http_utils 迁出）。

启动路径负责把版本化的 demo 素材复制到上传目录；不依赖引擎层。
"""

from __future__ import annotations

import shutil
from pathlib import Path

DEMO_FRENCHIE_PROFILE_PHOTO = "demo/frenchie-profile.png"
DEMO_FRENCHIE_POSTCARD_PHOTO = "demo/frenchie-netcafe-postcard.png"


def ensure_demo_media(upload_dir: Path) -> None:
    # 版本化的 demo 素材（随代码/镜像分发）优先；data/uploads/demo 兼容旧部署
    candidate_dirs = (
        Path(__file__).resolve().parent / "assets" / "demo",
        Path(__file__).resolve().parents[1] / "data" / "uploads" / "demo",
    )
    target_dir = upload_dir / "demo"
    for filename in (DEMO_FRENCHIE_PROFILE_PHOTO, DEMO_FRENCHIE_POSTCARD_PHOTO):
        target = target_dir / Path(filename).name
        if target.exists():
            continue
        for source_dir in candidate_dirs:
            source = source_dir / Path(filename).name
            if source.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                break
