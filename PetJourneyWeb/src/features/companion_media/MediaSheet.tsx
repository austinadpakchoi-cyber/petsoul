import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CompanionSession, ParticipationMode } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { currentLeg } from "@/shared/journey/vehicle";
import { positionAt } from "@/shared/media/anchor";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import type { JourneySheetProps } from "@/shared/slots/names";
import { formatClock } from "@/shared/time/clock";
import {
  Button,
  Chip,
  DataOriginBadge,
  ErrorState,
  Icon,
  LoadingState,
  Progress,
  Sheet,
} from "@/shared/ui";
import {
  deviceId,
  getMediaElement,
  joinSession,
  leaveSession,
  onSessionUpdate,
  onSheetCollapsed,
  playSolo,
  usePlayer,
} from "./playerStore";

const MODE_TEXT: Record<ParticipationMode, string> = {
  not_joined: "你还没加入",
  joining: "正在加入…",
  synced: "已同步 · 正在和 TA 一起",
  solo: "你在独立回听",
  buffering: "你这边在缓冲",
  blocked: "浏览器拦下了播放",
  failed: "播放失败",
  left: "你暂时离开了",
};

function VideoSlot({ active }: { active: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = ref.current;
    const el = getMediaElement();
    if (!active || !host || !(el instanceof HTMLVideoElement)) return;
    host.appendChild(el);
    return () => {
      if (el.parentElement === host) host.removeChild(el);
    };
  }, [active]);
  return <div ref={ref} className="ps-media-video-host" />;
}

function SessionBody({
  session,
  nowMs,
  driving,
}: {
  session: CompanionSession;
  nowMs: number;
  driving: boolean;
}) {
  const player = usePlayer();
  const { companionMedia } = useServices();
  const queryClient = useQueryClient();
  const isMine = player.sessionId === session.session_id;
  const mode: ParticipationMode = isMine ? player.mode : "not_joined";
  const petPosition = positionAt(
    session.anchor,
    session.state,
    session.media.duration_ms,
    nowMs,
  );
  const keyRef = useRef(newIdempotencyKey("media-cmd"));

  useEffect(() => onSessionUpdate(session), [session]);

  const command = useMutation({
    mutationFn: (kind: "pause" | "resume") =>
      companionMedia.command(
        session.session_id,
        {
          device_id: deviceId(),
          command: kind,
          session_revision: session.revision,
          position_ms: petPosition,
        },
        keyRef.current,
      ),
    onSuccess: (next) => {
      keyRef.current = newIdempotencyKey("media-cmd");
      queryClient.setQueryData(
        queryKeys.mediaSession(session.session_id),
        next,
      );
    },
    onError: () => {
      keyRef.current = newIdempotencyKey("media-cmd");
      void queryClient.invalidateQueries({
        queryKey: queryKeys.mediaSession(session.session_id),
      });
    },
  });

  const isVideo = session.media.kind === "video";
  const interrupted = session.state === "interrupted";
  const external = session.media.availability !== "in_app_sync";
  const unavailable =
    external || (isVideo && (driving || !session.video_allowed));
  const participating = isMine && ["synced", "buffering"].includes(mode);
  const paused = session.state === "paused";

  return (
    <div
      className="ps-stack ps-media-body"
      data-session-id={session.session_id}
      data-player-mode={mode}
      data-session-state={session.state}
    >
      <div className={`ps-media-heading ${isVideo ? "is-video" : ""}`}>
        <div className={`ps-media-cover ps-media-cover--${session.media.kind}`}>
          {isVideo && isMine && mode !== "failed" ? (
            <VideoSlot key={session.session_id} active />
          ) : session.media.poster_url ? (
            <img src={session.media.poster_url} alt="" />
          ) : (
            <Icon name={isVideo ? "tv" : "music"} size={32} />
          )}
        </div>
        <div>
          <div style={{ fontWeight: 700 }}>{session.media.title}</div>
          <div className="ps-muted">{session.media.creator ?? "作者未知"}</div>
        </div>
      </div>
      <div className="ps-media-progress">
        <span className="ps-muted">
          {participating ? "当前" : "TA 在"}{" "}
          {formatClock(participating ? player.localMs : petPosition)}
        </span>
        <Progress
          value={
            (participating ? player.localMs : petPosition) /
            session.media.duration_ms
          }
          label={
            participating
              ? "当前设备播放进度（不可拖动）"
              : "TA 的播放进度（不可拖动）"
          }
        />
        <span className="ps-muted">
          {formatClock(session.media.duration_ms)}
        </span>
      </div>
      <div className="ps-row">
        <Chip
          tone={
            mode === "synced"
              ? "leaf"
              : mode === "failed" || mode === "blocked"
                ? "danger"
                : "neutral"
          }
          data-testid="participation-mode"
        >
          {mode === "synced" && paused
            ? "已同步 · 一起暂停中"
            : MODE_TEXT[mode]}
        </Chip>
        {interrupted ? (
          <Chip tone="sky">
            已保存到{" "}
            {formatClock(
              session.saved_progress_ms ?? session.anchor.position_ms,
            )}
          </Chip>
        ) : null}
      </div>
      {isMine && player.message ? (
        <p className="ps-muted" style={{ margin: 0 }} role="status">
          {player.message}
        </p>
      ) : null}
      {interrupted ? (
        <p className="ps-muted" style={{ margin: 0 }}>
          到站了，这段晚上接着看。交通不会等播放器，已按时下车。
        </p>
      ) : null}
      {external ? (
        <p className="ps-muted" style={{ margin: 0 }}>
          这部作品只能去外部平台打开，那边的进度无法同步，不会显示“一起”。
        </p>
      ) : null}

      <div className="ps-media-actions">
        {!interrupted && !unavailable && !participating ? (
          <Button
            variant="leaf"
            block
            loading={mode === "joining"}
            icon={isVideo ? "tv" : "music"}
            onClick={() => joinSession(session)}
          >
            {mode === "joining"
              ? "正在加入…"
              : mode === "failed" || mode === "blocked"
                ? "重试加入"
                : isVideo
                  ? "一起看"
                  : "一起听"}
          </Button>
        ) : null}
        {!interrupted && !unavailable && participating ? (
          <Button
            block
            variant="leaf"
            icon={paused ? "play" : "pause"}
            loading={command.isPending}
            onClick={() => command.mutate(paused ? "resume" : "pause")}
          >
            {paused ? "和 TA 一起继续" : "和 TA 一起暂停"}
          </Button>
        ) : null}
        <div className="ps-row">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => playSolo(session)}
            disabled={unavailable}
          >
            {isVideo ? "自己从头看" : "自己从头听"}
          </Button>
          {isMine && mode !== "left" && mode !== "not_joined" ? (
            <Button variant="ghost" onClick={leaveSession}>
              离开一起{isVideo ? "看" : "听"}
            </Button>
          ) : null}
        </div>
      </div>
      {!interrupted && !unavailable ? (
        <div className="ps-media-caption">
          <span>暂停的是播放，旅程会继续。进度条仅显示时间。</span>
          {command.isError ? (
            <Chip tone="danger">
              {toApiError(command.error).code === "VERSION_CONFLICT"
                ? "会话已更新，请重试"
                : "没能发出指令"}
            </Chip>
          ) : null}
        </div>
      ) : null}
      <DataOriginBadge
        origin={session.data_origin}
        label="内部测试音视频 · 未作公开发行授权"
      />
      {unavailable && isVideo && driving ? (
        <p className="ps-muted">TA 正在驾驶，不能一起看视频。</p>
      ) : null}
      {driving && !isVideo ? (
        <div className="ps-row">
          <Button
            size="sm"
            variant="secondary"
            icon="tv"
            disabled
            aria-describedby="drive-note"
          >
            换成看剧
          </Button>
          <span id="drive-note" className="ps-muted">
            TA 正在开车，只能听；停车休息后再一起看剧。
          </span>
        </div>
      ) : null}
    </div>
  );
}

export function MediaSheet({
  snapshot,
  nowMs,
  kind,
  targetId,
  close,
}: JourneySheetProps) {
  const { companionMedia } = useServices();
  const query = useQuery({
    queryKey: queryKeys.mediaSession(targetId),
    queryFn: () => companionMedia.session(targetId),
    enabled: kind === "media",
    refetchInterval: 15_000,
  });
  if (kind !== "media") return null;
  const leg = currentLeg(snapshot);
  const driving = leg?.role === "driver";
  const onClose = () => {
    onSheetCollapsed();
    close();
  };
  const title = query.data?.media.kind === "video" ? "一起看" : "一起听";
  return (
    <Sheet
      className="ps-media-sheet"
      title={title}
      subtitle={
        leg?.world_service
          ? `${leg.world_service.carrier_name} ${leg.world_service.service_code} 上`
          : "路上"
      }
      onClose={onClose}
    >
      {query.isPending ? (
        <LoadingState lines={2} />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <SessionBody session={query.data} nowMs={nowMs} driving={driving} />
      )}
    </Sheet>
  );
}
