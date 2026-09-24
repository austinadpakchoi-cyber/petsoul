/**
 * 通讯器 · 公告的钩子：公告列表（细条与公告页共用同一个查询键，进公告页时直接用细条已取到的结果）、
 * 已读记在哪个账号下、这个账号在本机的已读记录（localStorage；同页写入靠自定义事件、别的标签页靠 storage 事件，写完细条立刻跟着变）。
 */
import { useCallback, useMemo, useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { useServices } from "@/shared/services/registry";
import { useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import { announcementsKey, parseReadState, READ_CHANGED_EVENT, readAccountOf, readRawReadState, readStorageKey, type ReadMap } from "./announcements";

/** 公告很少变：一分钟内切来切去不重复请求；回到页面（窗口重新获得焦点）照常刷新。 */
const ANNOUNCEMENTS_STALE_MS = 60_000;

export function useAnnouncementFeed() {
  const { communicator } = useServices();
  const viewer = useOptionalCurrentHousehold()?.userId ?? null;
  return useQuery({
    queryKey: announcementsKey(viewer),
    queryFn: ({ signal }) => communicator.announcements(signal),
    staleTime: ANNOUNCEMENTS_STALE_MS,
  });
}

/** 已读记在哪个账号下：当前登录的用户编号；演示模式或拿不到时是 "fixture"。细条与公告页用同一个取法。 */
export function useAnnouncementReadAccount(): string {
  return readAccountOf(useOptionalCurrentHousehold()?.userId);
}

/** 这个账号在本机的已读记录（slug → revision）。读不到就是空的——全部当未读。 */
export function useAnnouncementReadMap(account: string): ReadMap {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const key = readStorageKey(account);
      const onStorage = (event: StorageEvent) => {
        if (event.key === null || event.key === key) onChange();
      };
      window.addEventListener("storage", onStorage);
      window.addEventListener(READ_CHANGED_EVENT, onChange);
      return () => {
        window.removeEventListener("storage", onStorage);
        window.removeEventListener(READ_CHANGED_EVENT, onChange);
      };
    },
    [account],
  );
  const snapshot = useCallback(() => readRawReadState(account), [account]);
  const raw = useSyncExternalStore(subscribe, snapshot, () => null);
  return useMemo(() => parseReadState(raw), [raw]);
}
