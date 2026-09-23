import { useEffect } from "react";
import { useSearchParams } from "react-router";
import type { JourneyOverlayProps } from "@/shared/slots/names";
import { Button, Icon } from "@/shared/ui";
import { useServices } from "@/shared/services/registry";
import {
  leaveSession,
  setParticipationReporter,
  teardown,
  usePlayer,
} from "./playerStore";

/**
 * 常驻迷你播放条：面板收起后音频继续，这里提供“展开 / 暂时离开”。
 * 离开旅途页时释放播放器（R0 行为；跨页后台播放由同行影音模块后续决定）。
 */
export function MediaDock(_props: JourneyOverlayProps) {
  const player = usePlayer();
  const { companionMedia } = useServices();
  const [params, setParams] = useSearchParams();
  useEffect(() => {
    setParticipationReporter(companionMedia);
    return () => {
      teardown();
      setParticipationReporter(null);
    };
  }, [companionMedia]);
  const sheetOpen = params.get("sheet")?.startsWith("media:");
  // 视频收起后你的播放已暂停（mode=left），仍保留一条提示，方便点开重新跟上。
  const videoPausedByCollapse =
    player.kind === "video" && player.mode === "left";
  if (
    !player.sessionId ||
    sheetOpen ||
    player.mode === "not_joined" ||
    (player.mode === "left" && !videoPausedByCollapse)
  )
    return null;
  const live =
    player.mode === "synced" ||
    player.mode === "solo" ||
    player.mode === "buffering";
  return (
    <div className="ps-dock" role="region" aria-label="迷你播放条">
      <span className={`ps-dock__icon${live ? " is-live" : ""}`}>
        <Icon name={player.kind === "video" ? "tv" : "music"} size={18} />
      </span>
      <button
        type="button"
        className="ps-dock__title"
        onClick={() => {
          const next = new URLSearchParams(params);
          next.set("sheet", `media:${player.sessionId}`);
          setParams(next);
        }}
      >
        <strong>{player.title}</strong>
        <span className="ps-muted">
          {player.mode === "synced"
            ? (player.message ?? "已同步 · 和 TA 一起")
            : player.mode === "solo"
              ? "独立回听"
              : player.mode === "buffering"
                ? "缓冲中"
                : videoPausedByCollapse
                  ? "你的视频已暂停 · 点开跟上"
                  : "未在播放"}
        </span>
      </button>
      <Button size="sm" variant="ghost" onClick={leaveSession}>
        离开
      </Button>
    </div>
  );
}
