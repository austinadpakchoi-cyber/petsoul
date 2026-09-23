import { afterEach, describe, expect, it, vi } from "vitest";
import type { CompanionSession } from "@/shared/contracts";
import { fixtureAudio } from "@/fixtures/media";
import { joinSession, leaveSession, setParticipationReporter, teardown } from "@/features/companion_media/playerStore";

function session(state: CompanionSession["state"]): CompanionSession {
  return {
    session_id: "ms-test-1",
    activity_id: "act-1",
    pet_id: "pet-1",
    media: fixtureAudio,
    state,
    anchor: { position_ms: 30_000, server_time: new Date().toISOString(), playback_rate: 1 },
    revision: 3,
    resume_policy: "save_shared_progress",
    control: null,
    saved_progress_ms: null,
    interrupt_reason: state === "paused" ? "joint_pause" : null,
    video_allowed: true,
    data_origin: "fixture",
  } as CompanionSession;
}

describe("companion participation reporting", () => {
  afterEach(() => {
    teardown();
    setParticipationReporter(null);
    vi.useRealTimers();
  });

  it("joins, heartbeats with the real player state and edition, and leaves", async () => {
    vi.useFakeTimers();
    const reporter = { join: vi.fn(async () => ({})), heartbeat: vi.fn(async () => ({})), leave: vi.fn(async () => ({})) };
    setParticipationReporter(reporter);
    joinSession(session("paused"));
    expect(reporter.join).toHaveBeenCalledWith("ms-test-1", expect.any(String));
    reporter.heartbeat.mockClear();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(reporter.heartbeat).toHaveBeenCalledTimes(1);
    const [, body] = reporter.heartbeat.mock.calls[0] as unknown as [string, { player_state: string; media_edition: string }];
    expect(body.player_state).toBe("synced");
    expect(body.media_edition).toBe(fixtureAudio.edition);
    leaveSession();
    expect(reporter.leave).toHaveBeenCalledWith("ms-test-1", expect.any(String));
    reporter.heartbeat.mockClear();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(reporter.heartbeat).not.toHaveBeenCalled();
  });

  it("an ended segment is not reported as synced", () => {
    const reporter = { join: vi.fn(async () => ({})), heartbeat: vi.fn(async () => ({})), leave: vi.fn(async () => ({})) };
    setParticipationReporter(reporter);
    joinSession(session("ended"));
    const states = reporter.heartbeat.mock.calls.map((c) => (c as unknown as [string, { player_state: string }])[1].player_state);
    expect(states).not.toContain("synced");
  });
});
