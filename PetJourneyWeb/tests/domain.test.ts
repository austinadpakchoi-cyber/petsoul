import { describe, expect, it } from "vitest";
import type { CareNote, LegTimes, MemoryGrant } from "@/shared/contracts";
import { legProgress, positionAlong } from "@/shared/journey/vehicle";
import { positionAt, participationCounts } from "@/shared/media/anchor";
import { buildHomeWelcome, projectMemory } from "@/shared/memory/policy";

describe("transport timeline mirror", () => {
  const times: LegTimes = {
    origin_timezone: "Asia/Shanghai",
    destination_timezone: "Asia/Shanghai",
    planned_departure_utc: "2026-09-22T06:20:00Z",
    planned_arrival_utc: "2026-09-22T08:55:00Z",
    estimated_departure_utc: null,
    estimated_arrival_utc: null,
    actual_departure_utc: null,
    actual_arrival_utc: null,
  };
  it("progress follows server time, not page-open time (75 of 155 minutes)", () => {
    expect(legProgress(times, Date.parse("2026-09-22T07:35:00Z"))).toBeCloseTo(75 / 155, 4);
  });
  it("a later estimated arrival slows progress instead of compressing the leg", () => {
    const delayed = { ...times, estimated_arrival_utc: "2026-09-22T09:30:00Z" };
    expect(legProgress(delayed, Date.parse("2026-09-22T07:35:00Z"))).toBeLessThan(legProgress(times, Date.parse("2026-09-22T07:35:00Z")));
  });
  it("interpolates along the route", () => {
    const { point, heading } = positionAlong([{ lat: 0, lng: 0 }, { lat: 0, lng: 2 }], 0.5);
    expect(point.lng).toBeCloseTo(1, 3);
    expect(heading).toBeCloseTo(90, 3);
  });
});

describe("media anchor mirror", () => {
  it("playing advances with server time; paused holds", () => {
    const anchor = { position_ms: 10_000, server_time: "2026-09-22T07:35:00Z", playback_rate: 1 };
    const later = Date.parse("2026-09-22T07:35:05Z");
    expect(positionAt(anchor, "playing", 60_000, later)).toBe(15_000);
    expect(positionAt(anchor, "paused", 60_000, later)).toBe(10_000);
  });
  it("only synced + fresh heartbeat + small drift counts as companionship", () => {
    expect(participationCounts("synced", "audio", 500, 5)).toBe(true);
    expect(participationCounts("solo", "audio", 0, 5)).toBe(false);
    expect(participationCounts("synced", "video", 0, 90)).toBe(false);
  });
});

describe("memory policy mirror", () => {
  const base = { pet_id: "p1", subject: "relationship" as const, version: 1, confirmed_at: "2026-09-22T00:00:00Z", supersedes_note_id: null, revoked_at: null };
  const notes: CareNote[] = [
    { ...base, note_id: "n-title", kind: "habit", text: "称呼主人为“姐姐”。", target: "give_to_pet", purposes: ["home_interaction"], slot: "owner_title", slot_value: "姐姐" },
    { ...base, note_id: "n-private", kind: "owner_private", text: "私人心里话", target: "give_to_pet", purposes: ["home_interaction"], slot: null, slot_value: null },
    { ...base, note_id: "n-keep", kind: "habit", text: "只留这里", target: "keep_here", purposes: [], slot: null, slot_value: null },
  ];
  const grants: MemoryGrant[] = notes.flatMap((n) => n.purposes.map((purpose) => ({ grant_id: `${n.note_id}-${purpose}`, note_id: n.note_id, note_version: 1, purpose, granted_at: base.confirmed_at, revoked_at: null })));

  it("private and unconfirmed content never reaches the pet projection", () => {
    const projection = projectMemory("p1", "home_interaction", notes, grants);
    expect(projection.items.map((i) => i.note_id)).toEqual(["n-title"]);
    const welcome = buildHomeWelcome(projection, 1, "c1");
    expect(welcome.greeting.startsWith("姐姐")).toBe(true);
    expect(JSON.stringify(welcome)).not.toContain("私人心里话");
  });

  it("revoking the grant removes the detail", () => {
    const revoked = grants.map((g) => ({ ...g, revoked_at: "2026-09-22T01:00:00Z" }));
    expect(projectMemory("p1", "home_interaction", notes, revoked).items).toEqual([]);
  });
});
