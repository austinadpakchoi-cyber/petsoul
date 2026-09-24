/**
 * 通讯模块（R0：私密通讯页 + 消息状态 fixture）。live 需适配既有 communicator 引擎，
 * client_message_id 作为幂等键，断网重发不产生重复消息。私密对话不进入星球圈。
 * 页面三个分区：我和 TA / 家庭来信（?channel=family）/ TA 的朋友（?channel=friends，见 FriendsSection）；
 * 同一排还有“朋友圈”入口，链到动态页 /circle（原“星球”标签退役后的去处；本模块只放入口，不改动态页）。
 * 公告（方案 7.1 / 11 节，GET /announcements）：顶上那一排在 320 宽下已满，不加第五个分段——入口是标题栏下面的一条细条
 * （AnnouncementStrip：有未读才着色，读完收成安静的一行，没有公告一行都不占）；全部公告在全屏页 /announcements（WorldGate 守）。
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import type { MessageDeliveryState, MessageSummary, MessageThread } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { defineModule } from "@/shared/modules/types";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useActiveHome, useCurrentHousehold } from "@/shared/session/householdContext";
import { Button, Chip, DataOriginBadge, EmptyState, Icon, Page, QueryView, TopBar } from "@/shared/ui";
import { fixtureThread } from "@/fixtures/social";
import { delay } from "@/fixtures/world";
import { WorldGate } from "@/features/world_map/WorldGate";
import { demoAnnouncementFeed, parseAnnouncementFeed } from "./announcements";
import { AnnouncementsPage } from "./AnnouncementsPage";
import { AnnouncementStrip } from "./AnnouncementStrip";
import { FriendsSection } from "./FriendsSection";
import "./communicator.css";

const STATE_TEXT: Record<MessageDeliveryState, string> = {
  sending: "发送中",
  delivered: "已送达 TA 的世界",
  awaiting_reply: "TA 晚点回你",
  processing: "照片冲洗中",
  failed: "没送出去",
};

function Composer({ petId }: { petId: string }) {
  const { communicator } = useServices();
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [clientId, setClientId] = useState(() => newIdempotencyKey("msg"));
  const send = useMutation({
    mutationFn: () => communicator.send(petId, { client_message_id: clientId, text }),
    onSuccess: () => {
      setText("");
      setClientId(newIdempotencyKey("msg"));
      void queryClient.invalidateQueries({ queryKey: ["communicator", "messages"] });
    },
  });
  return (
    <form
      className="ps-comm-composer"
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) send.mutate();
      }}
    >
      <input className="ps-input" value={text} onChange={(e) => setText(e.target.value)} placeholder="给 TA 捎句话…" aria-label="消息内容" maxLength={500} />
      <Button type="submit" variant="primary" icon="mail" loading={send.isPending} aria-label="发送" />
      {send.isError ? <Chip tone="danger">没送出去，点发送会用同一编号重试</Chip> : null}
    </form>
  );
}

function Bubble({ m, reply, hasGuide, hasCollection }: { m: MessageSummary; reply: MessageSummary | null; hasGuide: boolean; hasCollection: boolean }) {
  const journeyId = m.source_event_id?.split(":", 1)[0];
  return (
    <li className={`ps-msg ps-msg--${m.sender}`}>
      {reply ? <div className="ps-msg__reply">回复「{reply.text}」</div> : m.reply_to ? <div className="ps-msg__reply">回复较早的一条消息 · 原文未加载</div> : null}
      <div>{m.text}</div>
      {m.photo_url ? (
        <figure className="ps-msg__photo">
          <img src={m.photo_url} alt={m.photo_status === "ready" ? "TA 发来的虚构旅行自拍明信片" : "TA 发来的纸质明信片排版"} loading="lazy" />
          <figcaption>{m.photo_status === "ready" ? "AI 生成的虚构旅行自拍，不是真实到访照片" : "纸质明信片排版；目前没有生成自拍"}</figcaption>
        </figure>
      ) : m.photo_status === "processing" ? <div className="ps-msg__photo-pending">随信画面正在生成</div> : m.photo_status === "failed" ? <div className="ps-msg__photo-pending">随信画面未生成成功，文字已送达</div> : null}
      {m.source_event_id ? <div className="ps-msg__links"><span>来自这趟旅途</span>{hasGuide && journeyId ? <Link to={`/guides?journey=${encodeURIComponent(journeyId)}`}>这趟旅途的手账</Link> : null}{hasCollection ? <Link to={`/collection?source_event_id=${encodeURIComponent(m.source_event_id)}`}>相关收藏</Link> : null}</div> : null}
      <span className="ps-msg__state">{m.status_note || STATE_TEXT[m.state]}{m.channel === "family" ? " · 家庭频道" : ""}</span>
    </li>
  );
}

/** 页面分区沿用 ?channel=（各处已有 ?channel=family 的链接）；friends 不是消息频道，只借同一个参数切换。 */
type Section = "private" | "family" | "friends";
const sectionOf = (raw: string | null): Section => (raw === "family" || raw === "friends" ? raw : "private");

function CommunicatorPage() {
  const { communicator, economy, transport } = useServices();
  const { userId, pet } = useCurrentHousehold();
  const [params, setParams] = useSearchParams();
  const section = sectionOf(params.get("channel"));
  const channel = section === "family" ? "family" : "private";
  const setSection = (next: Section) => { const copy = new URLSearchParams(params); if (next === "private") copy.delete("channel"); else copy.set("channel", next); setParams(copy, { replace: true }); };
  const home = useActiveHome();
  const petId = home.data?.pet.pet_id;
  // 看“TA 的朋友”时不轮询消息；切回来先显示缓存，再按过期规则刷新。
  const thread = useQuery({ queryKey: queryKeys.messagesFor(userId ?? "-", petId ?? "-"), queryFn: () => communicator.thread(petId!), enabled: Boolean(petId) && section !== "friends", refetchInterval: 15_000 });
  const guides = useQuery({ queryKey: queryKeys.guidesFor(userId ?? "-", petId ?? "-"), queryFn: ({ signal }) => transport.guides(petId, signal), enabled: section === "family" && Boolean(petId && userId), retry: false });
  const collection = useQuery({ queryKey: queryKeys.collectionFor(userId ?? "-", petId ?? "-"), queryFn: ({ signal }) => economy.collection(petId, signal), enabled: section === "family" && Boolean(petId && userId), retry: false });
  const name = home.data?.pet.name;
  return (
    <Page>
      <TopBar
        title={home.data ? section === "family" ? `${name} 的家庭来信` : section === "friends" ? `${name} 的朋友` : `和 ${name} 的通讯` : "通讯"}
        subtitle={section === "family" ? "发给这个家的成员；彼此私聊仍保密" : section === "friends" ? "TA 自己在外面认识的朋友" : "只有你和 TA 看得到"}
        right={
          <Link className="ps-btn ps-btn--ghost ps-btn--sm" to="/onboarding/reception?mode=supplement">
            <Icon name="bookmark" size={16} /> 补充叮嘱
          </Link>
        }
      />
      <AnnouncementStrip />
      {/* 前三项是本页分区；“朋友圈”是去动态页（/circle，原“星球”标签退役后的去处）的入口，所以是链接、不是分区按钮。 */}
      <div className="ps-communicator-channels" role="group" aria-label="通讯器分区">
        <button type="button" aria-pressed={section === "private"} onClick={() => setSection("private")}>我和 TA</button>
        <button type="button" aria-pressed={section === "family"} onClick={() => setSection("family")}>家庭来信</button>
        <button type="button" aria-pressed={section === "friends"} onClick={() => setSection("friends")}>TA 的朋友</button>
        <Link to="/circle">朋友圈<Icon name="chevron" size={12} strokeWidth={2.2} /></Link>
      </div>
      {section === "friends" ? <FriendsSection petId={pet?.pet_id ?? petId ?? null} /> : <QueryView query={thread}>
        {(t: MessageThread) => (
          <>
            <ul className="ps-msgs">
              {t.items.filter((m) => (m.channel ?? "private") === channel).map((m) => (
                <Bubble key={m.message_id} m={m} reply={m.reply_to ? t.items.find((candidate) => candidate.message_id === m.reply_to) ?? null : null} hasGuide={Boolean(m.source_event_id && guides.data?.some((guide) => guide.journey_id === m.source_event_id?.split(":", 1)[0]))} hasCollection={Boolean(m.source_event_id && collection.data?.some((item) => item.source_event_id === m.source_event_id))} />
              ))}
            </ul>
            {t.items.every((m) => (m.channel ?? "private") !== channel) ? <EmptyState icon="mail" title={channel === "family" ? "家里还没有共同来信" : "你和 TA 还没有私聊"}>{channel === "family" ? "旅途中的世界事件会寄给全家；其他家人的私聊不会显示在这里。" : "给 TA 捎句话，回复会按照 TA 的状态稍后到达。"}</EmptyState> : null}
            <DataOriginBadge origin={t.data_origin} />
            {petId && channel === "private" ? <Composer petId={petId} /> : channel === "family" ? <p className="ps-communicator-family-note">家庭频道由 TA 的世界事件寄出；想单独聊天，请切回“我和 TA”。</p> : null}
          </>
        )}
      </QueryView>}
    </Page>
  );
}

export default defineModule({
  id: "communicator",
  routes: [{ path: "communicator", element: <CommunicatorPage /> }],
  // 公告页是二级页：全屏、不挂底栏，登录与入住守卫沿用 WorldGate（写法同 life 模块）。
  bareRoutes: [
    {
      path: "announcements",
      element: (
        <WorldGate>
          <AnnouncementsPage />
        </WorldGate>
      ),
    },
  ],
  services: {
    communicator: {
      fixture: () => {
        const sent: MessageSummary[] = [];
        return {
          thread: async (petId) => {
            const t = fixtureThread(petId);
            return delay({ ...t, items: [...t.items, ...sent] });
          },
          send: async (_petId, body) => {
            const existing = sent.find((m) => m.client_message_id === body.client_message_id);
            if (existing) return delay(existing);
            const m: MessageSummary = { message_id: `fx-m-${Date.now()}`, client_message_id: body.client_message_id, sender: "owner", text: body.text, state: "delivered", created_at: new Date().toISOString(), photo_url: null };
            sent.push(m);
            return delay(m);
          },
          // 演示公告：标题带“（演示）”，公告页在演示模式下另挂“演示公告”标识（契约的 source 没有“演示”这一值）——不冒充真实运营公告。
          announcements: async () => delay(demoAnnouncementFeed()),
        };
      },
      live: ({ api }) => ({
        thread: (petId) => api.request<MessageThread>(`/communicator/${encodeURIComponent(petId)}/messages`),
        send: (petId, body) => api.request<MessageSummary>(`/communicator/${encodeURIComponent(petId)}/messages`, { method: "POST", body }),
        // 契约已有 AnnouncementFeed，但路由还没挂 response_model（归运营后台），服务端暂不保证形状：
        // 先按 unknown 取回，再逐条解析成契约类型（坏条目丢掉，外层坏了抛可重试的错误）。
        announcements: async (signal) => parseAnnouncementFeed(await api.request<unknown>("/announcements", { signal })),
      }),
    },
  },
});
