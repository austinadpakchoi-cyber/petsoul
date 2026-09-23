/**
 * 通讯模块（R0：私密通讯页 + 消息状态 fixture）。live 需适配既有 communicator 引擎，
 * client_message_id 作为幂等键，断网重发不产生重复消息。私密对话不进入星球圈。
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
      className="ps-composer"
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

function CommunicatorPage() {
  const { communicator, economy, transport } = useServices();
  const { userId } = useCurrentHousehold();
  const [params, setParams] = useSearchParams();
  const channel = params.get("channel") === "family" ? "family" : "private";
  const setChannel = (next: "private" | "family") => { const copy = new URLSearchParams(params); if (next === "family") copy.set("channel", "family"); else copy.delete("channel"); setParams(copy, { replace: true }); };
  const home = useActiveHome();
  const petId = home.data?.pet.pet_id;
  const thread = useQuery({ queryKey: queryKeys.messagesFor(userId ?? "-", petId ?? "-"), queryFn: () => communicator.thread(petId!), enabled: Boolean(petId), refetchInterval: 15_000 });
  const guides = useQuery({ queryKey: queryKeys.guidesFor(userId ?? "-", petId ?? "-"), queryFn: ({ signal }) => transport.guides(petId, signal), enabled: channel === "family" && Boolean(petId && userId), retry: false });
  const collection = useQuery({ queryKey: queryKeys.collectionFor(userId ?? "-", petId ?? "-"), queryFn: ({ signal }) => economy.collection(petId, signal), enabled: channel === "family" && Boolean(petId && userId), retry: false });
  return (
    <Page>
      <TopBar
        title={home.data ? channel === "family" ? `${home.data.pet.name} 的家庭来信` : `和 ${home.data.pet.name} 的通讯` : "通讯"}
        subtitle={channel === "family" ? "发给这个家的成员；彼此私聊仍保密" : "只有你和 TA 看得到"}
        right={
          <Link className="ps-btn ps-btn--ghost ps-btn--sm" to="/onboarding/reception?mode=supplement">
            <Icon name="bookmark" size={16} /> 补充叮嘱
          </Link>
        }
      />
      <div className="ps-communicator-channels" role="group" aria-label="通讯频道"><button type="button" aria-pressed={channel === "private"} onClick={() => setChannel("private")}>我和 TA</button><button type="button" aria-pressed={channel === "family"} onClick={() => setChannel("family")}>家庭共同来信</button></div>
      <QueryView query={thread}>
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
      </QueryView>
    </Page>
  );
}

export default defineModule({
  id: "communicator",
  routes: [{ path: "communicator", element: <CommunicatorPage /> }],
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
        };
      },
      live: ({ api }) => ({
        thread: (petId) => api.request<MessageThread>(`/communicator/${encodeURIComponent(petId)}/messages`),
        send: (petId, body) => api.request<MessageSummary>(`/communicator/${encodeURIComponent(petId)}/messages`, { method: "POST", body }),
      }),
    },
  },
});
