import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CompanionSession } from "@/shared/contracts";
import { fixtureMediaSessions } from "@/fixtures/media";
import {
  getMediaElement,
  getPlayerState,
  joinSession,
  leaveSession,
  onSessionUpdate,
  setParticipationReporter,
  teardown,
} from "@/features/companion_media/playerStore";

const mediaSession = () =>
  Object.values(fixtureMediaSessions()).find(
    (s) => s.media.kind === "audio" && s.media.availability === "in_app_sync",
  )!;
function playing() {
  const el = getMediaElement()!;
  Object.defineProperty(el, "paused", { configurable: true, value: false });
  el.dispatchEvent(new Event("playing"));
}

describe("real player state boundaries", () => {
  beforeEach(() => {
    vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (
      this: HTMLMediaElement,
    ) {
      Object.defineProperty(this, "paused", {
        configurable: true,
        value: true,
      });
    });
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    vi.spyOn(HTMLMediaElement.prototype, "readyState", "get").mockReturnValue(
      4,
    );
    setParticipationReporter({
      join: async () => ({}),
      heartbeat: async () => ({}),
      leave: async () => ({}),
    });
  });
  afterEach(() => {
    teardown();
    setParticipationReporter(null);
    vi.restoreAllMocks();
  });
  it("requires actual playing, and swaps sources for same-kind sessions", async () => {
    const s = mediaSession();
    joinSession(s);
    await Promise.resolve();
    expect(getPlayerState().mode).toBe("joining");
    playing();
    expect(getPlayerState().mode).toBe("synced");
    const next: CompanionSession = {
      ...s,
      session_id: "another",
      media: { ...s.media, edition: "new-edition", src_url: "/other.m4a" },
    };
    joinSession(next);
    expect(getMediaElement()!.getAttribute("src")).toBe("/other.m4a");
    expect(getPlayerState().sessionId).toBe("another");
  });
  it("shows failed when joining the server session fails", async () => {
    setParticipationReporter({
      join: async () => {
        throw new Error("offline");
      },
      heartbeat: async () => ({}),
      leave: async () => ({}),
    });
    joinSession(mediaSession());
    playing();
    await Promise.resolve();
    await Promise.resolve();
    expect(getPlayerState().mode).toBe("failed");
    expect(getMediaElement()!.paused).toBe(true);
  });
  it("late playing events cannot rejoin after leaving", async () => {
    const s = mediaSession();
    joinSession(s);
    await Promise.resolve();
    playing();
    leaveSession();
    onSessionUpdate(s);
    getMediaElement()!.dispatchEvent(new Event("playing"));
    expect(getPlayerState().mode).toBe("left");
    expect(getMediaElement()!.paused).toBe(true);
  });
  it("reports buffer, local media error, and paused state honestly", async () => {
    const s = mediaSession();
    joinSession(s);
    await Promise.resolve();
    playing();
    getMediaElement()!.dispatchEvent(new Event("waiting"));
    expect(getPlayerState().mode).toBe("buffering");
    playing();
    onSessionUpdate({
      ...s,
      state: "paused",
      anchor: { ...s.anchor, position_ms: 12_000 },
    });
    expect(getMediaElement()!.paused).toBe(true);
    expect(getPlayerState().localMs).toBe(12_000);
    getMediaElement()!.dispatchEvent(new Event("error"));
    expect(getPlayerState().mode).toBe("failed");
  });
});
