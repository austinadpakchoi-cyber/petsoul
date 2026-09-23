import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useCurrentHousehold } from "@/shared/session/householdContext";
import { EmptyState, ErrorState, LoadingState, Page, TopBar } from "@/shared/ui";
import "./life.css";

export function CredentialPage() {
  const { credentialId } = useParams();
  const { life } = useServices();
  const { userId, pet } = useCurrentHousehold();
  const petId = pet?.pet_id ?? "";
  const list = useQuery({ queryKey: queryKeys.credentialsFor(userId ?? "-", petId), queryFn: ({ signal }) => life.credentials(petId, signal), enabled: Boolean(userId && petId) });
  const own = list.data?.some((item) => item.credential_id === credentialId) ?? false;
  const detail = useQuery({ queryKey: queryKeys.credentialFor(userId ?? "-", petId, credentialId ?? "-"), queryFn: ({ signal }) => life.credential(credentialId!, signal), enabled: Boolean(credentialId && own) });
  return <Page className="ps-life-page"><TopBar title="星球证件" subtitle="只属于当前这只伙伴" back="/life" /><div className="ps-life-content">{list.isPending ? <LoadingState label="正在确认这张证件的归属…" /> : list.isError ? <ErrorState error={list.error} onRetry={() => void list.refetch()} /> : !own ? <EmptyState icon="lock" title="这不是当前宠物的证件">切回对应的伙伴，或返回生活档案。</EmptyState> : detail.isPending ? <LoadingState label="正在翻开证件…" /> : detail.isError ? <ErrorState error={detail.error} onRetry={() => void detail.refetch()} /> : detail.data ? <><section className={`ps-life-card ps-life-card--${detail.data.summary.kind}`}><span>PETSOUL · OFFICIAL RECORD</span><h1>{detail.data.summary.label}</h1><p>{pet?.name}</p><strong>{detail.data.summary.number ?? "尚未签发编号"}</strong><small>{detail.data.summary.issued_at ? `签发于 ${new Date(detail.data.summary.issued_at).toLocaleDateString("zh-CN")}` : detail.data.summary.condition}</small></section>{detail.data.fields.length ? <section className="ps-life-detail"><h2>卡面资料</h2>{detail.data.fields.map((field) => <div key={field.label}><span>{field.label}</span><strong>{field.value}</strong></div>)}</section> : null}{detail.data.summary.kind === "bank_card" ? <section className="ps-life-detail"><h2>星球银行卡</h2><p>与家园钱包是同一个账户，不另加一份余额。</p><div className="ps-life-balance">{detail.data.balance == null ? "余额暂不可用" : `${detail.data.balance} 星币`}</div><h3>最近收支</h3>{detail.data.ledger.length ? detail.data.ledger.map((entry) => <div key={entry.tx_id} className="ps-life-ledger"><span>{entry.reason}<small>{new Date(entry.created_at).toLocaleString("zh-CN")}</small>{entry.ref_kind && entry.ref_id ? <small>关联 {entry.ref_kind} · {entry.ref_id}</small> : null}</span><strong>{entry.delta > 0 ? "+" : ""}{entry.delta}</strong></div>) : <p>还没有收支记录。</p>}</section> : null}{detail.data.stamps.length ? <section className="ps-life-detail"><h2>旅途盖章</h2>{detail.data.stamps.map((stamp) => <div key={stamp.journey_id}><span>{stamp.city}</span><strong>{stamp.title}</strong></div>)}</section> : null}{detail.data.care_notes.length ? <section className="ps-life-detail"><h2>只给主人看的照护叮嘱</h2>{detail.data.care_notes.map((note, index) => <p key={`${index}-${note}`}>{note}</p>)}</section> : null}{detail.data.summary.links.length ? <section className="ps-life-detail"><h2>这张证件关联的经历</h2>{detail.data.summary.links.map((link) => <div key={`${link.kind}-${link.ref_id}`}><span>{link.kind}</span><strong>{link.title}</strong></div>)}</section> : null}<Link className="ps-life-back" to="/life">← 返回生活档案</Link></> : null}</div></Page>;
}
