"""同行影音作品目录。首发只有 R0 用 ffmpeg 合成的自制测试素材（无第三方内容），许可状态 self_generated_test：
能在应用内播放，但不代表同步已验收或可公开发布。热门歌曲/剧集需另行取得授权并按平台能力接入。"""

from __future__ import annotations

from ..schemas.web.common import DataOrigin
from ..schemas.web.companion_media import LicenseStatus, MediaAsset, MediaAvailability, MediaKind, MediaLicense

_TEST_LICENSE = MediaLicense(
    status=LicenseStatus.self_generated_test,
    allows_in_app_playback=True,
    allows_sync=False,
    public_release_allowed=False,
    regions=[],
    expires_at=None,
    note="自制合成测试素材：用于验证播放与失败路径，非授权作品库",
)

MUSIC = MediaAsset(
    media_id="media-melody-01",
    kind=MediaKind.audio,
    title="窗边的小调",
    creator="PetSoul 测试素材",
    edition="melody-v1",
    duration_ms=150_000,
    src_url="/fixtures/media/fixture-melody.m4a",
    poster_url=None,
    external_url=None,
    availability=MediaAvailability.in_app_sync,
    license=_TEST_LICENSE,
    data_origin=DataOrigin.live,
)

VIDEO = MediaAsset(
    media_id="media-clip-01",
    kind=MediaKind.video,
    title="云上色块 第 1 集",
    creator="PetSoul 测试素材",
    edition="clip-v1",
    duration_ms=90_000,
    src_url="/fixtures/media/fixture-clip.mp4",
    poster_url=None,
    external_url=None,
    availability=MediaAvailability.in_app_sync,
    license=_TEST_LICENSE,
    data_origin=DataOrigin.live,
)

ASSETS = {MUSIC.media_id: MUSIC, VIDEO.media_id: VIDEO}
