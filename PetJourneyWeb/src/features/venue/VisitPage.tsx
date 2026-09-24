import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import type { PetPrivateSummary, Visit, VisitActivity, VisitActivityKind, VisitState } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useActiveHome } from "@/shared/session/householdContext";
import { Slot } from "@/shared/slots/Slot";
import { Button, Card, Chip, DataOriginBadge, EmptyState, ErrorState, Icon, LoadingState, Page, QueryView, TopBar, type IconName } from "@/shared/ui";
import { CafeScene } from "./CafeScene";
import "./venue.css";

const STATE_TEXT: Record<VisitState, string> = {
  planned: "计划中",
  travelling: "在路上",
  arrived: "刚到",
  active: "在店里",
  completed: "已离店",
  cancelled: "已取消",
};

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
        {activity.label}
      </Button>
      {activity.result_text ? <p className="ps-muted" role="status">{activity.result_text}</p> : null}
    </div>
  );
}

function VisitBody({ visit, pet }: { visit: Visit; pet: PetPrivateSummary | null }) {
  const seated = visit.activities.some((a) => a.kind === "choose_seat" && a.state === "done");
  return (
    <div className="ps-stack">
      <CafeScene visit={visit} pet={pet} seated={seated} />
      <div className="ps-visit-state">
        <Chip tone="leaf">{STATE_TEXT[visit.state]}</Chip>
        {pet ? <span className="ps-visit-state__story">{pet.name} 的到店手帐</span> : null}
        <DataOriginBadge origin={visit.data_origin} label="演示到访" />
      </div>
      <div className="ps-visit-acts">
        {visit.activities.map((a) => (
          <ActivityButton key={a.activity_id} visit={visit} activity={a} />
        ))}
      </div>
      {visit.activities.some((activity) => activity.kind === "take_photo" && activity.state === "done") ? <Link className="ps-visit-memento-link" to="/communicator?channel=family"><Icon name="mail" size={17} /> 去家庭来信查看这次留念与照片状态 <Icon name="chevron" size={15} /></Link> : null}
      <Link className="ps-visit-memento-link" to="/photos"><Icon name="camera" size={17} /> 查看其他场景的照片申请与结果 <Icon name="chevron" size={15} /></Link>
      <Card flat>
        <div className="ps-section-title" style={{ marginTop: 0 }}>
          {visit.place.provider === "fixture" ? "商家资料（演示）" : "商家资料"}
        </div>
        <div style={{ fontWeight: 700 }}>{visit.place.name}</div>
        <div className="ps-muted">地址：{visit.place.address ?? "未提供"} · 来源：{visit.place.attribution ?? visit.place.provider}</div>
        <div className="ps-muted">店内画面是动物世界的原创场景，不代表这家店的真实装修、菜单或宠物准入。</div>
      </Card>
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
      <TopBar title={query.data?.place.name ?? "店里"} subtitle="到店活动" back="/map" />
      <QueryView query={query}>{(visit) => home.isPending ? <LoadingState label="正在确认当前宠物…" /> : home.isError ? <ErrorState error={home.error} onRetry={() => void home.refetch()} /> : home.data?.pet.pet_id !== visit.pet_id ? <EmptyState icon="lock" title="这不是当前宠物的到访">切回这次出门的伙伴，才能看见 TA 的店内活动。</EmptyState> : <VisitBody visit={visit} pet={home.data.pet} />}</QueryView>
    </Page>
  );
}
