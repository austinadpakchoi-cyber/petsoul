import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import type { HouseholdDetail, PhotoRequestResult, PhotoRequestView, PhotoScene } from "@/shared/contracts";
import { isApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { currentLeg } from "@/shared/journey/vehicle";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useActiveHome, useCurrentHousehold } from "@/shared/session/householdContext";
import { EmptyState, ErrorState, Icon, LoadingState, Page, TopBar } from "@/shared/ui";
import { beginPhotoIntent, photoIntentStillUncertain, readPhotoIntent, sendPhotoIntent, type PendingPhotoIntent } from "./photoIntent";
import "./pets.css";

const SCENES: { scene: PhotoScene; title: string; kicker: string; detail: string; fiction: boolean }[] = [
  { scene: "home", title: "在家拍一张", kicker: "01 / 此刻的家", detail: "TA 真的在家时，记录一个平常瞬间。", fiction: false },
  { scene: "train", title: "列车上拍一张", kicker: "02 / 真实旅程", detail: "只在 TA 真的处于列车行程段时成立。", fiction: false },
  { scene: "flight_adventure", title: "想象一次飞行冒险", kicker: "03 / 虚构主题", detail: "明确是幻想照片；不写入真实旅程、不扣星币、不发勋章。", fiction: true },
];
const STATUS: Record<string, { title: string; detail: string }> = {
  processing: { title: "正在生成", detail: "这张还在画，过一会儿可以刷新结果。" },
  ready: { title: "照片已完成", detail: "这是一张动物世界的生活照片，不是现实地点实拍。" },
  failed: { title: "没画成", detail: "这张没有画成。如果愿意，可以亲自点一次重画。" },
  unknown: { title: "结果还没确认", detail: "这张可能已经开始制作；不会悄悄再画一张。你可以稍后刷新，或亲自决定重画。" },
};

export type PhotoRetryNote = { scope: string; requestId: string; status: PhotoRequestView["photo_status"]; text: string };
export function currentPhotoRetryNote(note: PhotoRetryNote | null, rows: PhotoRequestView[] | undefined, scope: string): string | null {
  return note?.scope === scope && rows?.find((item) => item.request_id === note.requestId)?.photo_status === note.status ? note.text : null;
}

export function currentPhotoRequestNotice(result: PhotoRequestResult, rows: PhotoRequestView[] | undefined): string | null {
  if (!result.task_id) return "现在还拍不了这张，也没有照片在等待。稍后再试。";
  if (rows?.some((item) => item.request_id === result.request_id)) return null;
  return "申请已经送达。请刷新下方结果，看看这张照片现在怎样了。";
}

export function PhotoFeedback({ error, scene }: { error: unknown; scene: PhotoScene }) {
  if (photoIntentStillUncertain(error)) return <p className="ps-photo-feedback" role="alert">这张的结果还没确认。可以先刷新照片列表；若要继续确认，下面的按钮会接着处理同一张，不会换成另一张。</p>;
  if (isApiError(error) && error.status === 409) return <p className="ps-photo-feedback" role="alert">{scene === "home" ? "TA 现在不能在家拍这张。" : scene === "train" ? "TA 现在不在列车上。" : "这个主题此刻不能拍。"}请等状态变化后再试。</p>;
  if (isApiError(error) && error.status === 403) return <p className="ps-photo-feedback" role="alert">你现在没有照顾 TA 的权限，不能申请这张照片。</p>;
  return <p className="ps-photo-feedback" role="alert">这张暂时拍不了，请稍后再试。</p>;
}

export function PhotoConsentNotice({ detail }: { detail: Pick<HouseholdDetail, "settings" | "your_permissions"> }) {
  if (detail.settings.generated_photos) return null;
  const canManage = detail.your_permissions.includes("manage");
  return <aside className="ps-photo-consent" role="note"><strong>这个家还没开启 AI 照片</strong><p>需要家庭管理员先允许使用 TA 的参考照片制作照片。开启后，TA 的生活事件也可能触发制作，不只是在这里点“拍一张”。</p>{canManage ? <Link to="/households/manage">去家庭设置开启 →</Link> : <p>请家庭管理员到“我们的家”开启；你目前只能查看这项许可。</p>}</aside>;
}

/** 演示模式里本来就没有这一项（演示服务答“能力未接入”）：给一句明确的说明，不当成出错，也不让人重试。live 的“能力未接入”照旧走统一错误态。 */
export function demoGap(error: unknown): boolean {
  return env.dataMode === "fixture" && isApiError(error) && error.isCapabilityUnavailable;
}

export function canRequestPhoto(scene: PhotoScene, photoAllowed: boolean, atHome: boolean, actualTrain: boolean, hasPendingIntent: boolean): boolean {
  return hasPendingIntent || (photoAllowed && (scene === "flight_adventure" || (scene === "home" ? atHome : actualTrain)));
}

export function PhotoRequestCard({ item, onRetry, retrying }: { item: PhotoRequestView; onRetry: (id: string) => void; retrying: boolean }) {
  const scene = SCENES.find((entry) => entry.scene === item.scene);
  const state = STATUS[item.photo_status] ?? { title: "状态待确认", detail: "请稍后刷新。" };
  return <article className="ps-photo-result">
    {item.photo_status === "ready" && item.image_url ? <figure><img src={item.image_url} alt={`${item.fictional ? "明确虚构主题" : "动物世界"}生成照片`} loading="lazy" /><figcaption>{item.fictional ? "虚构飞行冒险 · 不是真实旅程" : "生成的动物世界照片 · 不是现实店铺实拍"}</figcaption></figure> : <div className={`ps-photo-result__empty ps-photo-result__empty--${item.photo_status}`}><Icon name="camera" size={27} /><span>{state.title}</span></div>}
    <div className="ps-photo-result__body"><div className="ps-photo-result__heading"><strong>{scene?.title ?? item.scene}</strong><small>{new Date(item.captured_at).toLocaleString("zh-CN")}</small></div><p>{state.detail}</p><p>{item.place} · {item.city}{item.fictional ? " · 虚构主题" : ""}</p>{item.can_retry && (item.photo_status === "failed" || item.photo_status === "unknown") ? <button type="button" disabled={retrying} onClick={() => onRetry(item.request_id)}>{retrying ? "正在提交…" : "我决定重画这张"}</button> : null}</div>
  </article>;
}

export function PhotoRequestsPage() {
  const { pets, transport, households } = useServices();
  const { userId, pet, household } = useCurrentHousehold();
  const petId = pet?.pet_id ?? "";
  const householdId = household?.household_id ?? "";
  const [params] = useSearchParams();
  const initial = params.get("scene");
  const [chosen, setChosen] = useState<PhotoScene>(initial === "train" || initial === "flight_adventure" ? initial : "home");
  const [result, setResult] = useState<{ scope: string; value: PhotoRequestResult } | null>(null);
  const [pending, setPending] = useState<PendingPhotoIntent | null>(() => userId && petId ? readPhotoIntent(userId, petId) : null);
  const [retryNote, setRetryNote] = useState<PhotoRetryNote | null>(null);
  const queryClient = useQueryClient();
  const scope = `${userId ?? "-"}:${petId}`;
  const scopeRef = useRef(scope);
  scopeRef.current = scope;
  useEffect(() => {
    const restored = userId && petId ? readPhotoIntent(userId, petId) : null;
    setPending(restored);
    if (restored) setChosen(restored.body.scene);
    setResult(null);
    setRetryNote(null);
  }, [userId, petId]);
  const activePending = pending?.userId === userId && pending.petId === petId ? pending : null;
  const home = useActiveHome({ refetchInterval: 30_000 });
  // 演示模式没有账号与家庭（HouseholdProvider 给的 userId、household、pet 都是 null）：照 useActiveHome 的写法，演示下不因 userId 为空而停用
  // （键的账号位是 "-"），照样问演示服务——有数据就显示，答“能力未接入”就明说演示里没有；以前这两处在演示里永远停在读取中。
  // 照片记录按演示家园快照里的那只宠物读（与“回忆”页同一个键）。live 的键、请求与启用条件一点不变。
  const fixture = env.dataMode === "fixture";
  const photoPermission = useQuery({ queryKey: queryKeys.householdDetail(userId ?? "-", householdId), queryFn: ({ signal }) => households.detail(householdId, signal), enabled: fixture || Boolean(userId && householdId) });
  const permissionDemo = demoGap(photoPermission.error);
  const permissionChecking = photoPermission.isPending || photoPermission.isFetching;
  const photoAllowed = !permissionChecking && !photoPermission.isError && photoPermission.data?.settings.generated_photos === true;
  const away = home.data?.presence !== "at_home" && Boolean(home.data?.journey);
  const map = useQuery({ queryKey: queryKeys.journeyMap(petId), queryFn: () => transport.journeyMap(petId), enabled: Boolean(petId && away), refetchInterval: away ? 30_000 : false });
  const actualTrain = map.data ? currentLeg(map.data)?.mode === "train" : false;
  const atHome = home.data?.presence === "at_home" && !home.data?.journey;
  const listPetId = fixture ? (home.data?.pet.pet_id ?? "") : petId;
  const list = useQuery({ queryKey: queryKeys.photoRequestsFor(userId ?? "-", listPetId), queryFn: ({ signal }) => pets.photoRequests(listPetId, signal), enabled: fixture ? !home.isPending : Boolean(userId && petId) });
  const request = useMutation({ mutationFn: (intent: PendingPhotoIntent) => sendPhotoIntent(pets, intent), onSuccess: (accepted, intent) => { const intentScope = `${intent.userId}:${intent.petId}`; if (scopeRef.current === intentScope) { setPending(null); setResult({ scope: intentScope, value: accepted }); } if (accepted.task_id) void queryClient.invalidateQueries({ queryKey: queryKeys.photoRequestsFor(intent.userId, intent.petId) }); }, onError: (error, intent) => { if (!photoIntentStillUncertain(error) && scopeRef.current === `${intent.userId}:${intent.petId}`) setPending(null); } });
  const retry = useMutation({ mutationFn: ({ petId: targetPetId, requestId }: { userId: string; petId: string; requestId: string }) => pets.retryPhoto(targetPetId, requestId), onSuccess: (rows, action) => { const actionScope = `${action.userId}:${action.petId}`; const updated = rows.find((item) => item.request_id === action.requestId); if (updated && scopeRef.current === actionScope) setRetryNote({ scope: actionScope, requestId: action.requestId, status: updated.photo_status, text: updated.photo_status === "processing" && updated.task_id ? "这张还在画，过一会儿刷新看看。" : updated.photo_status === "ready" ? "这张已经画好了，可以在下面查看。" : updated.photo_status === "unknown" ? "这张的结果还没确认，稍后刷新看看。" : "这张暂时没有新结果，稍后刷新看看。" }); queryClient.setQueryData(queryKeys.photoRequestsFor(action.userId, action.petId), rows); } });
  const selected = SCENES.find((entry) => entry.scene === chosen)!;
  const enabled = canRequestPhoto(chosen, photoAllowed, atHome, actualTrain, Boolean(activePending));
  const visibleRetryNote = currentPhotoRetryNote(retryNote, list.data, scope);
  const visibleRequestNotice = result?.scope === scope ? currentPhotoRequestNotice(result.value, list.data) : null;
  const requestInScope = request.variables && `${request.variables.userId}:${request.variables.petId}` === scope;
  const retryInScope = retry.variables && `${retry.variables.userId}:${retry.variables.petId}` === scope;
  const requestBusy = Boolean(requestInScope && request.isPending);
  return <Page className="ps-photo-page"><TopBar title={`${pet?.name ?? "TA"} 的照片`} subtitle="申请、结果和重画都在这里" back="/memories" /><div className="ps-photo-content">
    <header className="ps-photo-hero"><h1>留住 TA<br />正在生活的一刻</h1><p>普通生活与想象中的冒险，分开记录。</p></header>
    <section className="ps-photo-scenes" aria-label="选择拍摄场景">{SCENES.map((entry) => <button key={entry.scene} type="button" disabled={requestBusy || Boolean(activePending)} aria-pressed={chosen === entry.scene} onClick={() => { setChosen(entry.scene); setResult(null); request.reset(); }}><small>{entry.kicker}</small><strong>{entry.title}</strong><span>{entry.detail}</span></button>)}</section>
    <section className="ps-photo-command"><div><strong>{selected.title}</strong><p>{activePending ? "上一次拍照还没收到明确答复。继续确认同一张，不会重复发起另一张。" : permissionChecking ? "先确认这个家的照片许可，再决定能否拍摄。" : permissionDemo ? "演示模式里拍不了真实照片，这里先看看有哪些拍法。" : photoPermission.isError ? "暂时读不到照片许可，请先重试。" : !photoAllowed ? "这个家还没开启 AI 照片，先确认家庭许可。" : selected.fiction ? "这是你主动选的虚构飞行主题，不会写成 TA 实际出行。" : chosen === "home" ? atHome ? "TA 此刻在家，可以试着留下一张。" : "TA 此刻不在家，这张要等回家后拍。" : actualTrain ? "TA 此刻正在列车上，可以试着拍一张。" : "TA 此刻不在列车上，这张要等上车后拍。"}</p></div>{permissionChecking ? <LoadingState label="正在确认这个家的照片许可…" /> : permissionDemo ? null : photoPermission.isError ? <ErrorState error={photoPermission.error} onRetry={() => void photoPermission.refetch()} /> : photoPermission.data ? <PhotoConsentNotice detail={photoPermission.data} /> : null}{home.isPending ? <LoadingState label="正在确认 TA 此刻的位置…" /> : home.isError ? <ErrorState error={home.error} onRetry={() => void home.refetch()} /> : chosen === "train" && map.isError ? <ErrorState error={map.error} onRetry={() => void map.refetch()} /> : null}<button type="button" disabled={!enabled || requestBusy} onClick={() => { if (!userId || !petId) return; const intent = beginPhotoIntent(userId, petId, chosen, activePending); setPending(intent); setChosen(intent.body.scene); setResult(null); request.mutate(intent); }}>{requestBusy ? "正在送出…" : activePending ? "用同一请求确认结果" : photoPermission.data && !photoAllowed && !permissionChecking && !photoPermission.isError ? "等待家庭许可" : "给我拍一张"}</button>{request.isError && requestInScope ? <PhotoFeedback error={request.error} scene={activePending?.body.scene ?? chosen} /> : null}{visibleRequestNotice ? <p className="ps-photo-feedback" role="status">{SCENES.find((entry) => entry.scene === result?.value.scene)?.title ?? "这次申请"}：{visibleRequestNotice}</p> : null}</section>
    <div className="ps-photo-cafe-note"><Icon name="cup" size={19} /><p>咖啡馆合影是另一条到店活动。{home.data?.journey?.current_visit_id ? <Link to={`/visits/${encodeURIComponent(home.data.journey.current_visit_id)}`}>回到 TA 此刻的店内 →</Link> : <Link to="/journey">去旅途看看 →</Link>}</p></div>
    <section className="ps-photo-list"><div className="ps-photo-list__title"><div><span>照片结果</span><h2>申请记录</h2></div><button type="button" onClick={() => void list.refetch()} disabled={list.isFetching}>{list.isFetching ? "正在刷新…" : "刷新结果"}</button></div>{visibleRetryNote ? <p role="status" className="ps-photo-feedback">{visibleRetryNote}</p> : null}{retry.isError && retryInScope ? <p role="alert" className="ps-photo-feedback">{"还没确认这次重画的结果。请刷新列表查看，或稍后再试。"}</p> : null}{list.isPending ? <LoadingState label="正在读取照片结果…" /> : demoGap(list.error) ? <EmptyState icon="camera" title="演示模式没有照片记录">住进来以后，给 TA 拍的照片会在这里。</EmptyState> : list.isError ? <ErrorState error={list.error} onRetry={() => void list.refetch()} /> : list.data?.length ? list.data.map((item) => <PhotoRequestCard key={item.request_id} item={item} retrying={Boolean(retryInScope && retry.isPending && retry.variables?.requestId === item.request_id)} onRetry={(id) => { if (!userId || !petId) return; setRetryNote(null); retry.mutate({ userId, petId, requestId: id }); }} />) : <EmptyState icon="camera" title="还没有照片结果">拍下的照片会出现在这里。暂时拍不了的场景不会留下空白记录。</EmptyState>}</section>
  </div></Page>;
}
