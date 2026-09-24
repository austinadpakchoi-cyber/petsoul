import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router";
import type { TravelGuide } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useCurrentHousehold } from "@/shared/session/householdContext";
import { Card, EmptyState, ErrorState, Icon, LoadingState, Page, QueryView, TopBar } from "@/shared/ui";
import { PlanShelf, useShelfViews } from "./travelPlan/PlanPage";
import "./guide.css";

const STATUS_TEXT: Record<string, string> = { planned: "还在计划", in_progress: "正在路上", completed: "已回家" };

function dateLabel(iso: string): string {
  return new Date(iso).toLocaleDateString("zh-CN", { month: "long", day: "numeric" });
}

function useGuides() {
  const { transport } = useServices();
  const { userId, pet } = useCurrentHousehold();
  return useQuery({
    queryKey: queryKeys.guidesFor(userId ?? "-", pet?.pet_id ?? "-"),
    queryFn: ({ signal }) => transport.guides(pet?.pet_id, signal),
    // 演示世界的家庭上下文没有当前用户和宠物：只看 userId && pet 时演示下这条查询永远不发，“去过的”一直是骨架屏（TRV-06 修）。
    enabled: env.dataMode === "fixture" || Boolean(userId && pet),
  });
}

export function GuideBookPage() {
  const { pet } = useCurrentHousehold();
  const [params] = useSearchParams();
  const journeyId = params.get("journey");
  const guides = useGuides();
  // TRV-06：列表分两块，“想去 / 准备中”（心愿与计划卡片）在上，“去过的”（下面这份原有攻略列表）在下。
  // 现在只有演示数据：live 接口未接时 useShelfViews() 为 null，这一块不显示、页面与原来一样；只看某一趟旅程（?journey=）时也不显示。
  const shelf = useShelfViews();
  const plans = journeyId ? null : shelf;
  const pastId = useId();
  const past = <QueryView query={guides} isEmpty={(list) => list.length === 0 && !journeyId} empty={<EmptyState icon="bookmark" title="还没有攻略手账">TA 准备好一趟旅程后，手账会出现在这里。</EmptyState>}>
      {(list) => {
        const visible = journeyId ? list.filter((guide) => guide.journey_id === journeyId) : list;
        return visible.length === 0 ? <EmptyState icon="bookmark" title="这趟旅程还没有手账">目前没有与这趟行程关联的攻略，不代 TA 编一份。<Link to="/guides">查看全部手账</Link></EmptyState> : <div className="ps-guide-list">{visible.map((guide) => <Link key={guide.guide_id} to={`/guides/${encodeURIComponent(guide.guide_id)}`} className="ps-guide-cover"><span className="ps-guide-cover__eyebrow">PETSOUL · TRAVEL NOTES</span><span className="ps-guide-cover__city">{guide.city}</span><strong>{guide.title}</strong><span className="ps-guide-cover__meta">{dateLabel(guide.created_at)} · {STATUS_TEXT[guide.status ?? ""] ?? "状态待确认"}</span><span className="ps-guide-cover__open">翻开手账 <Icon name="chevron" size={15} /></span></Link>)}</div>;
      }}
    </QueryView>;
  return <Page className="ps-guide-page">
    <TopBar title={`${pet?.name ?? "TA"} 的攻略手账`} subtitle="计划与已经发生的事，分开写" back="/memories" />
    <div className="ps-guide-intro"><Icon name="bookmark" size={23} /><div><strong>翻开 TA 的旅行笔记</strong><p>真实地址只显示服务端核对过的地点；未核实的叫法只留在故事里。</p></div></div>
    {plans ? <PlanShelf views={plans} /> : null}
    {plans ? <section className="ps-plan-shelf" aria-labelledby={pastId} data-shelf="past"><div className="ps-plan-shelf__head"><h2 id={pastId}>去过的</h2></div>{past}</section> : past}
  </Page>;
}

function GuideContent({ guide }: { guide: TravelGuide }) {
  const [copyState, setCopyState] = useState("");
  const copy = async () => {
    if (!guide.copy_text) return;
    try { await navigator.clipboard.writeText(guide.copy_text); setCopyState("已复制核实资料"); }
    catch { setCopyState("浏览器未允许复制，请手动选取下方文字"); }
  };
  return <div className="ps-guide-content">
    <header className="ps-guide-hero"><span>TA 的旅行手账 · {guide.city}</span><h1>{guide.title}</h1><p>{guide.summary || "这份手账暂时没有序言。"}</p><small>{STATUS_TEXT[guide.status ?? ""] ?? "状态待确认"} · {guide.composed_by === "model" ? "TA 的语气整理" : "规则模板整理"}</small></header>
    {guide.image_url && guide.image_status === "ready" ? <figure className="ps-guide-image"><img src={guide.image_url} alt="TA 的虚构旅行手账插画" /><figcaption>AI 生成的虚构手账图；路线与地址请以文字中已核实的资料为准。</figcaption></figure> : <div className="ps-guide-image-state"><Icon name="bookmark" size={28} /><span>{guide.image_status === "processing" ? "手账插画正在生成" : guide.image_status === "failed" ? "手账插画未生成成功，文字仍可阅读" : guide.image_status === "unknown" ? "手账插画状态待确认" : "这一页只有文字，没有生成插画"}</span></div>}
    <div className="ps-guide-budget">{guide.coin_budget != null ? <span>星球内计划花费：{guide.coin_budget} 星币</span> : null}{guide.real_budget_note ? <span>现实费用：{guide.real_budget_note}</span> : null}</div>
    <h2>沿途停靠</h2>
    {guide.stops.length ? <ol className="ps-guide-stops">{guide.stops.map((stop, index) => <li key={`${stop.name}-${index}`}><span className="ps-guide-stops__number">{String(index + 1).padStart(2, "0")}</span><div><div className="ps-guide-stops__heading"><strong>{stop.label || stop.name}</strong><small>{stop.verified ? "地点已核实" : "地点未核实"}{guide.visited?.includes(stop.name) ? " · TA 已到过" : ""}</small></div>{stop.time ? <p>{stop.time}</p> : null}{stop.why ? <p>{stop.why}</p> : null}{stop.verified && stop.address ? <address>{stop.name} · {stop.address}</address> : null}{stop.tip ? <p className="ps-guide-stops__tip">{stop.tip}</p> : null}{stop.attribution ? <small>来源：{stop.attribution}</small> : null}{stop.verified && stop.nav_url?.startsWith("https://") ? <a href={stop.nav_url} target="_blank" rel="noopener noreferrer">打开地点导航 ↗</a> : null}</div></li>)}</ol> : <EmptyState icon="pin" title="还没有停靠点">TA 暂时没有写出可展示的站点。</EmptyState>}
    {guide.owner_tips.length ? <Card paper className="ps-guide-tips"><strong>家人留给 TA 的话</strong>{guide.owner_tips.map((tip, index) => <p key={`${index}-${tip}`}>{tip}</p>)}</Card> : null}
    {guide.copy_text ? <section className="ps-guide-copy"><div><strong>给家人照着走的文字版</strong><button type="button" onClick={() => void copy()}>复制核实资料</button></div>{copyState ? <p role="status">{copyState}</p> : null}<textarea readOnly value={guide.copy_text} aria-label="攻略文字版" rows={6} /></section> : null}
  </div>;
}

export function GuideDetailPage() {
  const { guideId } = useParams();
  const { transport } = useServices();
  const guides = useGuides();
  const belongsToCurrentPet = guides.data?.some((guide) => guide.guide_id === guideId) ?? false;
  const detail = useQuery({ queryKey: queryKeys.guide(guideId ?? "-"), queryFn: ({ signal }) => transport.guide(guideId!, signal), enabled: Boolean(guideId && belongsToCurrentPet) });
  return <Page className="ps-guide-page"><TopBar title="旅行手账" back="/guides" />
    {guides.isPending ? <LoadingState label="正在确认 TA 的手账…" /> : guides.isError ? <ErrorState error={guides.error} onRetry={() => void guides.refetch()} /> : !belongsToCurrentPet ? <EmptyState icon="lock" title="这不是当前宠物的手账">切回对应的伙伴，或返回手账列表。</EmptyState> : detail.isPending ? <LoadingState label="正在翻开手账…" /> : detail.isError ? <ErrorState error={detail.error} onRetry={() => void detail.refetch()} /> : detail.data ? <GuideContent guide={detail.data} /> : null}
  </Page>;
}
