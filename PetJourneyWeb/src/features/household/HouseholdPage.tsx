import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import type { HouseholdDetail, HouseholdInvite, HouseholdSettingsRequestInput } from "@/shared/contracts";
import { isApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { householdLabel, useCurrentHousehold, useHouseholdLabels } from "@/shared/session/householdContext";
import { Card, EmptyState, ErrorState, LoadingState, Page, PetAvatar, TopBar } from "@/shared/ui";
import { MembersCard } from "./MembersCard";
import "./household.css";

/**
 * 出错原因给玩家看的一句（2026-09-24 巡检 P1 追加）：接口错误用 ApiError.playerMessage（还没开放、后端没有这条路的换成人话，
 * 其余照用后端写给玩家的原话）；不是接口错误的（前端自己的异常）不显示异常原文。
 */
export function failure(error: unknown): string {
  return isApiError(error) ? error.playerMessage : "操作暂时没有完成，请重试。";
}

/** 把一句原因接进整句：原因自己以句号、问号、叹号或省略号收尾就不再补句号，免得出现“。。”。 */
export function withStop(text: string): string {
  const trimmed = text.trim();
  return /[。！？!?…]$/.test(trimmed) ? trimmed : `${trimmed}。`;
}

/** 演示模式里本来就没有这一项（演示服务答“能力未接入”）：明说演示里没有，不当成出错。live 的“能力未接入”照旧走统一错误态。 */
function demoGap(error: unknown): boolean { return env.dataMode === "fixture" && isApiError(error) && error.isCapabilityUnavailable; }

export function photoSettingResultUncertain(error: unknown): boolean {
  return !isApiError(error) || error.status === null || error.status >= 500 || error.status === 408 || error.status === 429;
}

export function PhotoConsentSetting({ enabled, canManage, pending, error, uncertain = false, checking = false, checkError = null, onChange, onRefresh }: { enabled: boolean; canManage: boolean; pending: boolean; error: unknown; uncertain?: boolean; checking?: boolean; checkError?: unknown; onChange: (enabled: boolean) => void; onRefresh?: () => void }) {
  const next = !enabled;
  const resultUncertain = uncertain || Boolean(error && photoSettingResultUncertain(error));
  return <Card paper className="ps-family-card ps-family-photo-consent">
    <div className="ps-family-photo-consent__heading"><div><span>照片许可</span><h2>AI 生活照片</h2></div><strong role="status">{resultUncertain ? "待确认" : enabled ? "已开启" : "未开启"}</strong></div>
    <p>开启后，可以使用 TA 的参考照片制作 AI 生活照片；TA 的真实生活事件也可能触发制作，不限于你主动点“拍一张”。关闭后不再许可新的照片制作。</p>
    <p className="ps-family-fine">这是家庭照片用途的许可，不是星币或玩家充值；能否实际制作仍取决于照片服务是否开放。</p>
    {resultUncertain ? <><p role="alert">保存结果未确认。不要重复开启或关闭；先只读刷新家庭状态，再决定下一步。</p>{onRefresh ? <button type="button" disabled={checking} onClick={onRefresh}>{checking ? "正在核对…" : "刷新当前许可"}</button> : null}{checkError ? <p role="alert">还没读到最新状态，请稍后再刷新。</p> : null}</> : canManage ? <button type="button" disabled={pending} onClick={() => { if (window.confirm(next ? "开启后，TA 的生活事件也可能触发 AI 照片制作。确定为这个家开启吗？" : "关闭后，这个家不再许可新的 AI 照片制作。确定关闭吗？")) onChange(next); }}>{pending ? "正在保存…" : next ? "明确开启照片制作" : "关闭照片制作"}</button> : <p>只有家庭管理员可以修改这项许可。你可以查看当前状态。</p>}
    {error && !resultUncertain ? <p role="alert">这次没有完成保存：{withStop(failure(error))}请以当前家庭状态为准。</p> : null}
  </Card>;
}

function FamilyContent({ detail, invites, reload }: { detail: HouseholdDetail; invites: HouseholdInvite[]; reload: () => void }) {
  const { households } = useServices();
  const { userId, pet } = useCurrentHousehold();
  const labels = useHouseholdLabels(userId);
  const queryClient = useQueryClient();
  const householdId = detail.household.household_id;
  // 起了名用详情里的名字（改名后最先拿到新值）；没起名与切换栏同一套说法：“{第一只已入住宠物}的家”，撞名带序号，还没有已入住的才叫“家庭 N”。
  const title = detail.household.name?.trim() || labels?.get(householdId) || householdLabel(detail.household, 0);
  const canManage = detail.your_permissions.includes("manage");
  const [name, setName] = useState(detail.settings.name ?? "");
  const [relationHint, setRelationHint] = useState("");
  const [newLink, setNewLink] = useState("");
  const [copyMessage, setCopyMessage] = useState("");
  const [ownerTitle, setOwnerTitle] = useState("");
  const [relationLabel, setRelationLabel] = useState("");
  const [photoUncertain, setPhotoUncertain] = useState(false);
  const [photoCheckPending, setPhotoCheckPending] = useState(false);
  const [photoCheckError, setPhotoCheckError] = useState<unknown>(null);
  const relationship = useQuery({ queryKey: queryKeys.householdRelationship(userId ?? "-", pet?.pet_id ?? "-"), queryFn: () => households.relationship(pet!.pet_id), enabled: Boolean(userId && pet) });
  useEffect(() => { if (relationship.data) { setOwnerTitle(relationship.data.owner_title ?? ""); setRelationLabel(relationship.data.relation_label ?? ""); } }, [relationship.data]);
  useEffect(() => setName(detail.settings.name ?? ""), [detail.settings.name]);
  const refresh = () => { void queryClient.invalidateQueries({ queryKey: queryKeys.householdDetail(userId ?? "-", householdId) }); void queryClient.invalidateQueries({ queryKey: queryKeys.householdInvites(userId ?? "-", householdId) }); void queryClient.invalidateQueries({ queryKey: queryKeys.households(userId ?? "-") }); reload(); };
  async function verifyPhotoSetting() {
    setPhotoCheckPending(true);
    setPhotoCheckError(null);
    try {
      const latest = await households.detail(householdId);
      queryClient.setQueryData(queryKeys.householdDetail(userId ?? "-", householdId), latest);
      setPhotoUncertain(false);
      settings.reset();
    } catch (error) { setPhotoCheckError(error); }
    finally { setPhotoCheckPending(false); }
  }
  const settings = useMutation({ mutationFn: (patch: HouseholdSettingsRequestInput) => households.updateSettings(householdId, patch), onSuccess: (updated, patch) => { queryClient.setQueryData(queryKeys.householdDetail(userId ?? "-", householdId), updated); if (patch.generated_photos !== undefined) { setPhotoUncertain(false); setPhotoCheckError(null); } refresh(); }, onError: (error, patch) => { if (patch.generated_photos !== undefined && photoSettingResultUncertain(error)) { setPhotoUncertain(true); void verifyPhotoSetting(); } } });
  // 称呼与“TA 的档案”（/me/dna）里的 owner_title 是同一份（后端同一张 web_pet_relationships）：保存后两边的缓存一起失效。
  const saveRelationship = useMutation({ mutationFn: () => households.saveRelationship(pet!.pet_id, { owner_title: ownerTitle.trim() || null, relation_label: relationLabel.trim() || null }), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: queryKeys.householdRelationship(userId ?? "-", pet?.pet_id ?? "-") }); void queryClient.invalidateQueries({ queryKey: queryKeys.dnaFor(userId ?? "-", pet?.pet_id ?? "-") }); } });
  const createInvite = useMutation({ mutationFn: () => households.createInvite(householdId, relationHint.trim() || null), onSuccess: (created) => { setNewLink(`${window.location.origin}${created.join_path}`); refresh(); } });
  const revoke = useMutation({ mutationFn: (id: string) => households.revokeInvite(householdId, id), onSuccess: refresh });
  return <div className="ps-family-content">
    <section className="ps-family-hero"><span>家庭档案</span><h1>{title}</h1><p>{detail.household.pets.length} 位伙伴 · {detail.members.length} 位家人</p></section>
    <Card paper className="ps-family-card"><h2>住在这里</h2><div className="ps-family-pets">{detail.household.pets.map((memberPet) => <div key={memberPet.pet_id}><PetAvatar petId={memberPet.pet_id} name={memberPet.name} species={memberPet.species} photoUrl={memberPet.photo_url} size={42} /><span>{memberPet.name}</span></div>)}</div><Link to="/home">回家看看 →</Link></Card>
    <MembersCard detail={detail} userId={userId} />
    <Card paper className="ps-family-card"><h2>{pet?.name ?? "TA"} 怎么称呼你</h2>{relationship.isPending ? <LoadingState label="正在读取你们的称呼…" /> : relationship.isError ? <ErrorState error={relationship.error} onRetry={() => void relationship.refetch()} /> : <><label>TA 对你的称呼<input value={ownerTitle} onChange={(event) => setOwnerTitle(event.target.value)} maxLength={12} placeholder="例如：妈妈" /></label><label>你们的关系<input value={relationLabel} onChange={(event) => setRelationLabel(event.target.value)} maxLength={12} placeholder="例如：家人" /></label><button type="button" disabled={saveRelationship.isPending} onClick={() => saveRelationship.mutate()}>{saveRelationship.isPending ? "保存中…" : "保存称呼"}</button>{saveRelationship.isSuccess ? <p role="status">称呼已保存，只用于你与 TA 的关系。</p> : null}{saveRelationship.isError ? <p role="alert">{failure(saveRelationship.error)}</p> : null}</>}</Card>
    <Card paper className="ps-family-card"><h2>家里的约定</h2>{canManage ? <><label>家名<input value={name} onChange={(event) => setName(event.target.value)} maxLength={48} /></label><button type="button" disabled={settings.isPending || name === (detail.settings.name ?? "")} onClick={() => settings.mutate({ name: name.trim() || null })}>保存家名</button><div className="ps-family-switches"><label><input type="checkbox" checked={detail.settings.caregivers_can_spend} disabled={settings.isPending} onChange={(event) => settings.mutate({ caregivers_can_spend: event.target.checked })} />共同照顾者可以使用 TA 的星球账户</label><label><input type="checkbox" checked={detail.settings.pet_messages} disabled={settings.isPending} onChange={(event) => settings.mutate({ pet_messages: event.target.checked })} />把 TA 的生活新鲜事寄到家庭频道</label><label><input type="checkbox" checked={detail.settings.public_posts} disabled={settings.isPending} onChange={(event) => settings.mutate({ public_posts: event.target.checked })} />允许 TA 的到访故事出现在公开朋友圈</label></div>{settings.isError && settings.variables?.generated_photos === undefined ? <p role="alert">{failure(settings.error)}</p> : null}</> : <p>你可以查看家里的约定；只有管理员能修改。</p>}</Card>
    <PhotoConsentSetting enabled={detail.settings.generated_photos} canManage={canManage} pending={settings.isPending} error={settings.isError && settings.variables?.generated_photos !== undefined ? settings.error : null} uncertain={photoUncertain} checking={photoCheckPending} checkError={photoCheckError} onRefresh={() => { void verifyPhotoSetting(); }} onChange={(enabled) => settings.mutate({ generated_photos: enabled })} />
    <Card paper className="ps-family-card"><h2>邀请家人</h2>{canManage ? <><p>邀请只授予共同照顾者角色。链接只显示这一次，请自己妥善转交。</p><label>给家人的称呼提示<input value={relationHint} onChange={(event) => setRelationHint(event.target.value)} placeholder="例如：爸爸（不影响权限）" maxLength={12} /></label><button type="button" disabled={createInvite.isPending} onClick={() => createInvite.mutate()}>{createInvite.isPending ? "正在生成…" : "生成 72 小时邀请链接"}</button>{newLink ? <div className="ps-family-created"><label>这次生成的专属链接<input readOnly value={newLink} onFocus={(event) => event.target.select()} /></label><button type="button" onClick={() => { void navigator.clipboard.writeText(newLink).then(() => setCopyMessage("已复制，请只发给受邀家人。"), () => setCopyMessage("复制失败，请选中上方链接手动复制。")); }}>复制链接</button>{copyMessage ? <p role="status">{copyMessage}</p> : null}</div> : null}{createInvite.isError ? <p role="alert">{failure(createInvite.error)}</p> : null}{invites.filter((invite) => invite.status === "pending").map((invite) => <div className="ps-family-row" key={invite.invite_id}><div><strong>{invite.relation_hint || "一位家人"}</strong><small>待加入 · 到期 {new Date(invite.expires_at).toLocaleString("zh-CN")}</small></div><button type="button" disabled={revoke.isPending} onClick={() => { if (window.confirm("撤销这份邀请？原链接将不能再使用。")) revoke.mutate(invite.invite_id); }}>撤销</button></div>)}{revoke.isError ? <p role="alert">{failure(revoke.error)}</p> : null}</> : <p>请让家庭管理员发出邀请。</p>}</Card>
  </div>;
}

export function HouseholdPage() {
  const { households } = useServices();
  const { userId, household } = useCurrentHousehold();
  const householdId = household?.household_id ?? "";
  // 演示模式没有账号与家庭（HouseholdProvider 给的是 null）：照 useActiveHome 的写法，演示下不因 userId 为空而停用（键的账号位是 "-"），
  // 照样问演示服务——有数据就显示，答“能力未接入”就明说演示里没有；不再误说“还没有家庭”。live 的键与启用条件一点不变。
  const fixture = env.dataMode === "fixture";
  const detail = useQuery({ queryKey: queryKeys.householdDetail(userId ?? "-", householdId), queryFn: ({ signal }) => households.detail(householdId, signal), enabled: fixture || Boolean(userId && householdId) });
  const invites = useQuery({ queryKey: queryKeys.householdInvites(userId ?? "-", householdId), queryFn: () => households.invites(householdId), enabled: Boolean(userId && householdId && detail.data?.your_permissions.includes("manage")) });
  return <Page className="ps-family-page"><TopBar title="我们的家" subtitle="同一个家，彼此有各自的角色" back="/me" />{!fixture && !householdId ? <EmptyState icon="home" title="还没有家庭">先让伙伴入住，家会出现在这里。</EmptyState> : detail.isPending ? <LoadingState label="正在翻开家庭档案…" /> : demoGap(detail.error) ? <EmptyState icon="home" title="演示模式没有真实的家庭资料">住进来以后，家人、邀请和约定都在这里。</EmptyState> : detail.isError ? <ErrorState error={detail.error} onRetry={() => void detail.refetch()} /> : detail.data ? <FamilyContent key={`${userId}:${householdId}`} detail={detail.data} invites={invites.data ?? []} reload={() => void detail.refetch()} /> : null}</Page>;
}
