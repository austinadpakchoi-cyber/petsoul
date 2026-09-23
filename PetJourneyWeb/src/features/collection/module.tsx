/**
 * 收藏与集市模块：回忆陈列（纪念品绑定宠物、不可交易；稀有种子可种）+ 集市（杂货铺收购与居民订单，都是 NPC）。
 * 玩家之间的挂牌交易未开放：不把 NPC 商店称为玩家市场。钱包只从服务端结果读取，不在前端自建余额或库存。
 */
import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import type { CollectionItem, InventoryItem, MarketResult, MarketView, ResidentOrder } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { defineModule } from "@/shared/modules/types";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useCurrentHousehold } from "@/shared/session/householdContext";
import { env } from "@/shared/config/env";
import { Button, Card, Chip, DataOriginBadge, EmptyState, Icon, Page, QueryView, TopBar } from "@/shared/ui";
import { fixtureFulfill, fixtureMarket, fixtureSell } from "@/fixtures/home";
import { fixtureCollection } from "@/fixtures/social";
import { delay } from "@/fixtures/world";
import "./collection.css";

const KIND_TEXT: Record<string, string> = { postcard: "明信片", seed: "稀有种子（可种进菜园）", badge: "勋章", shared_memory: "共同听看的回忆" };
const MARKET_KEY = ["economy", "market"] as const;

function CollectionPage() {
  const { economy } = useServices();
  const { userId, pet } = useCurrentHousehold();
  const [params] = useSearchParams();
  const sourceEventId = params.get("source_event_id");
  const petId = pet?.pet_id ?? null;
  const query = useQuery({
    queryKey: env.dataMode === "fixture" ? queryKeys.collection : queryKeys.collectionFor(userId ?? "-", petId ?? "-"),
    queryFn: ({ signal }) => economy.collection(petId, signal),
    enabled: env.dataMode === "fixture" || Boolean(petId && userId),
  });
  return (
    <Page>
      <TopBar
        title="回忆与收藏"
        back="/home"
        right={
          <Link to="/market" className="ps-btn ps-btn--ghost ps-btn--sm">
            <Icon name="coin" size={16} /> 集市
          </Link>
        }
      />
      <QueryView query={query} isEmpty={(l) => l.length === 0 && !sourceEventId} empty={<EmptyState icon="gift" title="还没有收藏">旅行带回的明信片、种子和勋章会陈列在这里。</EmptyState>}>
        {(items: CollectionItem[]) => (
          <div className="ps-stack">
            {sourceEventId ? <div className="ps-collection-filter"><span>只看这条旅途消息关联的收藏</span><Link to="/collection">查看全部</Link></div> : null}
            {(sourceEventId ? items.filter((item) => item.source_event_id === sourceEventId) : items).length === 0
              ? <EmptyState icon="mail" title="这段经历还没有收藏">目前没有与这条世界事件关联的明信片或纪念品；不替 TA 补一张。</EmptyState>
              : (sourceEventId ? items.filter((item) => item.source_event_id === sourceEventId) : items).map((item) => (
                <Card key={item.item_id} paper={item.kind === "postcard"} className="ps-collection-item">
                  <div className="ps-collection-item__head"><div><strong>{item.title}</strong><div className="ps-muted">{KIND_TEXT[item.kind] ?? item.kind}{item.place ? ` · ${item.place}` : ""}</div></div><DataOriginBadge origin={item.data_origin} /></div>
                  {item.kind === "postcard" ? <>
                    {item.image_url && item.image_status === "ready" ? <figure className="ps-collection-item__image"><img src={item.image_url} alt={`TA 从${item.place ?? item.city ?? "旅途"}寄来的虚构旅行自拍`} loading="lazy" /><figcaption>AI 生成的虚构旅行自拍，不是真实到店照片</figcaption></figure> : <div className="ps-collection-item__envelope" aria-label="明信片尚无可展示的自拍"><Icon name="mail" size={30} /><span>{item.image_status === "processing" ? "自拍冲洗中" : item.image_status === "failed" ? "自拍未生成成功" : item.image_status === "unknown" ? "自拍状态待确认" : "这张明信片没有自拍"}</span></div>}
                    {item.note ? <p className="ps-collection-item__note">“{item.note}”</p> : null}
                  </> : null}
                  <div className="ps-row" style={{ flexWrap: "wrap" }}>
                    {item.bound_to_pet ? <Chip>个人纪念，不可交易</Chip> : item.tradable ? <Chip tone="leaf">可种植</Chip> : null}
                  </div>
                </Card>
              ))}
          </div>
        )}
      </QueryView>
    </Page>
  );
}

function useMarketWrite() {
  const queryClient = useQueryClient();
  return (result: MarketResult) => {
    void queryClient.invalidateQueries({ queryKey: MARKET_KEY });
    // 跨模块失效：旅费与仓库都在家园快照里。
    void queryClient.invalidateQueries({ queryKey: queryKeys.home });
    return result;
  };
}

function PantryRow({ item }: { item: InventoryItem }) {
  const { economy } = useServices();
  const done = useMarketWrite();
  const keyRef = useRef(newIdempotencyKey("sell"));
  const sell = useMutation({
    mutationFn: (qty: number) => economy.sell(item.item_key, qty, keyRef.current),
    onSuccess: (result) => {
      keyRef.current = newIdempotencyKey("sell");
      done(result);
    },
  });
  return (
    <li className="ps-market-row">
      <div style={{ flex: 1, minWidth: 0 }}>
        <strong>
          {item.label} ×{item.qty}
        </strong>
        <div className="ps-muted">杂货铺收购价 {item.unit_price} 旅费/个</div>
        {sell.isError ? (
          <div role="alert" className="ps-muted" style={{ color: "var(--c-danger)" }}>
            {toApiError(sell.error).message}
          </div>
        ) : null}
      </div>
      {item.qty > 1 ? (
        <Button size="sm" variant="ghost" disabled={sell.isPending} onClick={() => sell.mutate(1)}>
          卖 1 个
        </Button>
      ) : null}
      <Button size="sm" variant="secondary" loading={sell.isPending} onClick={() => sell.mutate(item.qty)}>
        全卖 +{item.qty * item.unit_price}
      </Button>
    </li>
  );
}

function OrderRow({ order }: { order: ResidentOrder }) {
  const { economy } = useServices();
  const done = useMarketWrite();
  const keyRef = useRef(newIdempotencyKey("order"));
  const fulfill = useMutation({ mutationFn: () => economy.fulfill(order.order_id, keyRef.current), onSuccess: done });
  return (
    <li className="ps-market-row">
      <div style={{ flex: 1, minWidth: 0 }}>
        <strong>
          {order.resident}想要 {order.qty} 个{order.item_label}
        </strong>
        <div className="ps-muted">
          出价 {order.reward} 旅费（卖给杂货铺是 {order.shop_value}）· 今天有效
        </div>
        {fulfill.isError ? (
          <div role="alert" className="ps-muted" style={{ color: "var(--c-danger)" }}>
            {toApiError(fulfill.error).message}
          </div>
        ) : null}
      </div>
      {order.fulfilled ? (
        <Chip tone="leaf" icon="check">
          已交
        </Chip>
      ) : (
        <Button size="sm" variant="primary" disabled={!order.can_fulfill} loading={fulfill.isPending} onClick={() => fulfill.mutate()}>
          {order.can_fulfill ? "交货" : "还不够"}
        </Button>
      )}
    </li>
  );
}

function MarketPage() {
  const { economy } = useServices();
  const query = useQuery({ queryKey: MARKET_KEY, queryFn: () => economy.market() });
  return (
    <Page>
      <TopBar title="集市" subtitle="把仓库里的收成换成旅费" back="/home" />
      <QueryView query={query}>
        {(market) => (
          <div className="ps-stack">
            <Card className="ps-row ps-market-wallet" style={{ justifyContent: "space-between" }}>
              <span>
                <Icon name="coin" /> 旅费
              </span>
              <strong style={{ fontSize: "var(--fs-lg)" }}>{market.wallet.balance}</strong>
            </Card>
            <Card>
              <div className="ps-section-title" style={{ marginTop: 0 }}>
                仓库 · 杂货铺收购
              </div>
              {market.pantry.length === 0 ? (
                <EmptyState icon="sprout" title="仓库是空的">
                  去菜园收获，或者趁邻居家宠物出门时去摘一点。
                </EmptyState>
              ) : (
                <ul className="ps-market-list">
                  {market.pantry.map((item) => (
                    <PantryRow key={item.item_key} item={item} />
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <div className="ps-section-title" style={{ marginTop: 0 }}>
                居民订单
              </div>
              <p className="ps-muted" style={{ marginTop: 0 }}>
                星球居民是公共角色，不是真实玩家；每天两张订单，出价比杂货铺高。
              </p>
              <ul className="ps-market-list">
                {market.orders.map((order) => (
                  <OrderRow key={order.order_id} order={order} />
                ))}
              </ul>
            </Card>
            <Card flat className="ps-row">
              <Icon name="lock" />
              <span className="ps-muted">{market.player_listing_note}</span>
            </Card>
            <DataOriginBadge origin={market.data_origin} />
          </div>
        )}
      </QueryView>
    </Page>
  );
}

export default defineModule({
  id: "collection",
  routes: [
    { path: "collection", element: <CollectionPage /> },
    { path: "market", element: <MarketPage /> },
  ],
  services: {
    economy: {
      fixture: () => ({
        collection: () => delay(fixtureCollection()),
        market: () => delay(fixtureMarket()),
        sell: async (itemKey, qty, key) => delay(fixtureSell(itemKey, qty, key)),
        fulfill: async (orderId) => delay(fixtureFulfill(orderId)),
      }),
      live: ({ api }) => ({
        collection: (petId, signal) => api.request<CollectionItem[]>("/collection", { query: { pet_id: petId }, signal }),
        market: () => api.request<MarketView>("/market"),
        sell: (itemKey, qty, key) => api.request<MarketResult>("/market/sell", { method: "POST", body: { item_key: itemKey, qty }, idempotencyKey: key }),
        fulfill: (orderId, key) => api.request<MarketResult>(`/market/orders/${encodeURIComponent(orderId)}/fulfill`, { method: "POST", idempotencyKey: key }),
      }),
    },
  },
});
