import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import type { PetPrivateSummary, Visit, VisitActivity, VisitActivityKind } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useActiveHome } from "@/shared/session/householdContext";
import { Slot } from "@/shared/slots/Slot";
import { Button, Card, Chip, DataOriginBadge, EmptyState, ErrorState, Icon, LoadingState, Page, QueryView, TopBar, type IconName } from "@/shared/ui";
import { CafeScene } from "./CafeScene";
import { OutdoorScene } from "./OutdoorScene";
import { hasMerchantInfo, PROVIDER_TEXT, visitSetting, visitStateText, visitStory, visitSubtitle } from "./visitKind";
import "./venue.css";

const ACTIVITY_ICON: Record<VisitActivityKind, IconName> = { choose_seat: "seat", order_drink: "cup", take_photo: "camera", greet_resident: "heart" };

function ActivityButton({ visit, activity }: { visit: Visit; activity: VisitActivity }) {
  const { visits } = useServices();
  const queryClient = useQueryClient();
  const keyRef = useRef(newIdempotencyKey("visit"));
  const mutation = useMutation({
    mutationFn: () => visits.act(visit.visit_id, { activity_id: activity.activity_id }, keyRef.current),
    onSuccess: (next) => {
      keyRef.current = newIdempotencyKey("visit");
      queryClient.setQueryData(queryKeys.visit(visit.visit_id), next);
      void queryClient.invalidateQueries({ queryKey: queryKeys.collection });
      void queryClient.invalidateQueries({ queryKey: ["communicator", "messages"] });
      void queryClient.invalidateQueries({ queryKey: ["social", "feed"] });
    },
  });
  const done = activity.state === "done";
  return (
    <div className="ps-visit-act">
      <Button variant={done ? "secondary" : "primary"} icon={ACTIVITY_ICON[activity.kind]} loading={mutation.isPending} disabled={done || activity.state === "disabled"} onClick={() => mutation.mutate()}>
        <span className="ps-visit-act__label">{activity.label}</span>
      </Button>
      {activity.result_text ? <p className="ps-muted" role="status">{activity.result_text}</p> : null}
    </div>
  );
}

/**
 * 地点资料：有门店、有商家资料的才叫“商家资料”，并说明店内画面是原创场景；其余叫“关于这个地方”。
 * 没有的字段整行不显示（不写“未提供”）；来源用服务端给的中文署名，缺了才按来源类型补一句，不露 amap / world 这类代码。
 */
function PlaceCard({ visit }: { visit: Visit }) {
  const merchant = hasMerchantInfo(visit);
  const source = visit.place.attribution ?? PROVIDER_TEXT[visit.place.provider];
  return (
    <Card flat className="ps-visit-place">
      <div className="ps-section-title" style={{ marginTop: 0 }}>
        {merchant ? (visit.place.provider === "fixture" ? "商家资料（演示）" : "商家资料") : "关于这个地方"}
      </div>
      <div style={{ fontWeight: 700 }}>{visit.place.name}</div>
      {visit.place.address ? <div className="ps-muted">地址：{visit.place.address}</div> : null}
      {source ? <div className="ps-muted">{source}</div> : null}
      {merchant ? <div className="ps-muted">店内画面是动物世界的原创场景，不代表这家店的真实装修、菜单或宠物准入。</div> : null}
    </Card>
  );
}

function VisitBody({ visit, pet }: { visit: Visit; pet: PetPrivateSummary | null }) {
  const setting = visitSetting(visit);
  const seated = visit.activities.some((a) => a.kind === "choose_seat" && a.state === "done");
  return (
    <div className="ps-stack">
      {/* 画面按地点类型选：有门店的画店内，小路 / 公园画一小片户外，其他（进城逛逛、打工）不放场景图 */}
      {setting === "shop" ? <CafeScene visit={visit} pet={pet} seated={seated} /> : setting === "outdoor" ? <OutdoorScene visit={visit} pet={pet} resting={seated} /> : null}
      <div className="ps-visit-state">
        <Chip tone="leaf">{visitStateText(visit.state, setting)}</Chip>
        {pet ? <span className="ps-visit-state__story">{visitStory(setting, pet.name)}</span> : null}
        <DataOriginBadge origin={visit.data_origin} label="演示到访" />
      </div>
      <div className="ps-visit-acts">
        {visit.activities.map((a) => (
          <ActivityButton key={a.activity_id} visit={visit} activity={a} />
        ))}
      </div>
      {visit.activities.some((activity) => activity.kind === "take_photo" && activity.state === "done") ? <Link className="ps-visit-memento-link" to="/communicator?channel=family"><Icon name="mail" size={17} /> 去家庭来信查看这次留念与照片状态 <Icon name="chevron" size={15} /></Link> : null}
      <Link className="ps-visit-memento-link" to="/photos"><Icon name="camera" size={17} /> 查看其他场景的照片申请与结果 <Icon name="chevron" size={15} /></Link>
      <PlaceCard visit={visit} />
      <Slot name="venue.panels" props={{ visit }} />
      <Link to="/map" className="ps-btn ps-btn--secondary">
        <Icon name="journey" /> 回到地图
      </Link>
    </div>
  );
}

export function VisitPage() {
  const { visitId = "" } = useParams();
  const { visits } = useServices();
  const query = useQuery({ queryKey: queryKeys.visit(visitId), queryFn: () => visits.visit(visitId), refetchInterval: (state) => ["planned", "travelling", "arrived", "active"].includes(state.state.data?.state ?? "") ? 8_000 : false });
  const home = useActiveHome();
  return (
    <Page>
      <TopBar title={query.data?.place.name ?? "这次出门"} subtitle={query.data ? visitSubtitle(visitSetting(query.data)) : undefined} back="/map" />
      <QueryView query={query}>{(visit) => home.isPending ? <LoadingState label="正在确认当前宠物…" /> : home.isError ? <ErrorState error={home.error} onRetry={() => void home.refetch()} /> : home.data?.pet.pet_id !== visit.pet_id ? <EmptyState icon="lock" title="这不是当前宠物的到访">切回这次出门的伙伴，才能看见 TA 这次出门的活动。</EmptyState> : <VisitBody visit={visit} pet={home.data.pet} />}</QueryView>
    </Page>
  );
}
