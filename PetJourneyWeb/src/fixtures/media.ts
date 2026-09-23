/**
 * 同行影音 fixture。素材为 R0 用 ffmpeg 合成的自制测试音视频（public/fixtures/media/README.txt），
 * license.status=self_generated_test：能在页面播放 ≠ 已验收同步 ≠ 已获公开授权。
 */
import type { CompanionSession, MediaAsset, MediaLicense } from "@/shared/contracts";
import { atSec } from "./world";

const TEST_LICENSE: MediaLicense = {
  status: "self_generated_test",
  allows_in_app_playback: true,
  allows_sync: false,
  public_release_allowed: false,
  regions: [],
  expires_at: null,
  note: "R0 自制合成测试素材，仅用于验证播放器与失败路径",
};

export const fixtureAudio: MediaAsset = {
  media_id: "fx-media-melody",
  kind: "audio",
  title: "窗边的小调（测试音频）",
  creator: "PetSoul 测试素材",
  edition: "fx-melody-v1",
  duration_ms: 150_000,
  src_url: "/fixtures/media/fixture-melody.m4a",
  poster_url: null,
  external_url: null,
  availability: "in_app_sync",
  license: TEST_LICENSE,
  data_origin: "fixture",
};

export const fixtureVideo: MediaAsset = {
  media_id: "fx-media-clip",
  kind: "video",
  title: "云上色块 第 1 集（测试短片）",
  creator: "PetSoul 测试素材",
  edition: "fx-clip-v1",
  duration_ms: 90_000,
  src_url: "/fixtures/media/fixture-clip.mp4",
  poster_url: null,
  external_url: null,
  availability: "in_app_sync",
  license: TEST_LICENSE,
  data_origin: "fixture",
};

/** 故意指向不存在的文件：演示加载失败 → 面板内失败说明与重试，不显示“已同步”。 */
export const fixtureBrokenVideo: MediaAsset = {
  ...fixtureVideo,
  media_id: "fx-media-missing",
  title: "海上纪录片 第 2 集（测试：素材缺失）",
  edition: "fx-missing-v1",
  src_url: "/fixtures/media/does-not-exist.mp4",
};

export const fixtureExternalOnly: MediaAsset = {
  ...fixtureAudio,
  media_id: "fx-media-external",
  title: "外部平台歌曲（测试：仅外链）",
  edition: "fx-external",
  src_url: null,
  external_url: "https://example.com/",
  availability: "external_link",
  license: { ...TEST_LICENSE, allows_in_app_playback: false },
};

type SessionSeed = Omit<CompanionSession, "anchor"> & { anchorOffsetSec: number; anchorPositionMs: number };

function build(seed: SessionSeed): CompanionSession {
  const { anchorOffsetSec, anchorPositionMs, ...rest } = seed;
  return { ...rest, anchor: { position_ms: anchorPositionMs, server_time: atSec(anchorOffsetSec), playback_rate: 1 } };
}

export function fixtureMediaSessions(): Record<string, CompanionSession> {
  const base = { pet_id: "fx-pet-001", control: null, saved_progress_ms: null, interrupt_reason: null, data_origin: "fixture" as const };
  const list: CompanionSession[] = [
    build({ ...base, session_id: "fx-ms-flight", activity_id: "fx-act-flight-music", media: fixtureAudio, state: "playing", anchorOffsetSec: 0, anchorPositionMs: 6_000, revision: 3, resume_policy: "pet_continues", video_allowed: true }),
    build({ ...base, session_id: "fx-ms-train", activity_id: "fx-act-train-video", media: fixtureVideo, state: "playing", anchorOffsetSec: 0, anchorPositionMs: 4_000, revision: 1, resume_policy: "save_shared_progress", video_allowed: true }),
    build({ ...base, session_id: "fx-ms-drive", activity_id: "fx-act-drive-music", media: fixtureAudio, state: "playing", anchorOffsetSec: -5, anchorPositionMs: 0, revision: 2, resume_policy: "pet_continues", video_allowed: false }),
    build({ ...base, session_id: "fx-ms-paused", activity_id: "fx-act-paused-music", media: fixtureAudio, state: "paused", interrupt_reason: "joint_pause", anchorOffsetSec: -40, anchorPositionMs: 21_000, revision: 5, resume_policy: "pet_continues", video_allowed: true }),
    build({ ...base, session_id: "fx-ms-failed", activity_id: "fx-act-failed-video", media: fixtureBrokenVideo, state: "playing", anchorOffsetSec: 0, anchorPositionMs: 2_000, revision: 1, resume_policy: "save_shared_progress", video_allowed: true }),
    build({ ...base, session_id: "fx-ms-arrived", activity_id: "fx-act-arrived-video", media: fixtureVideo, state: "interrupted", interrupt_reason: "arrival", saved_progress_ms: 18_000, anchorOffsetSec: -120, anchorPositionMs: 18_000, revision: 4, resume_policy: "save_shared_progress", video_allowed: true }),
  ];
  return Object.fromEntries(list.map((s) => [s.session_id, s]));
}
