import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import type { CredentialSummary, JobRecord } from "@/shared/contracts";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useCurrentHousehold } from "@/shared/session/householdContext";
import { Card, EmptyState, ErrorState, LoadingState, Page, TopBar } from "@/shared/ui";
import "./life.css";

const STATUS: Record<string, string> = { active: "已持有", in_progress: "办理中", not_obtained: "尚未获得", used: "已使用", expired: "已过期" };

export function LifeHubPage() {
  const { life } = useServices();
  const { userId, pet } = useCurrentHousehold();
  const petId = pet?.pet_id ?? "";
  const jobs = useQuery({ queryKey: queryKeys.jobsFor(userId ?? "-", petId), queryFn: ({ signal }) => life.jobs(petId, signal), enabled: Boolean(userId && petId) });
  const credentials = useQuery({ queryKey: queryKeys.credentialsFor(userId ?? "-", petId), queryFn: ({ signal }) => life.credentials(petId, signal), enabled: Boolean(userId && petId) });
  return <Page className="ps-life-page"><TopBar title="TA 的生活档案" subtitle="工作和证件，只记真实发生的事" back="/home" /><div className="ps-life-content">
    <header className="ps-life-hero"><span>PETSOUL · EVERYDAY RECORDS</span><h1>{pet?.name ?? "TA"} 的日子<br />正在继续</h1><p>每一张证件、每一笔工资，都是这只伙伴自己的经历。</p></header>
    <section><div className="ps-life-section-title"><span>01 / 这阵子的工作</span><Link to="/journey">去旅途看看 →</Link></div>{jobs.isPending ? <LoadingState label="正在翻阅工作记录…" /> : jobs.isError ? <ErrorState error={jobs.error} onRetry={() => void jobs.refetch()} /> : jobs.data?.length ? <div className="ps-life-jobs">{jobs.data.map((job: JobRecord) => <Card paper key={`${job.journey_id}-${job.job_key}`} className="ps-life-job"><div><small>{job.status === "done" ? "已经做完" : job.status === "working" ? "正在工作" : "去上班的路上"}</small><strong>{job.title}</strong><span>{job.place ?? "地点未记录"}</span></div><div className="ps-life-job__pay"><b>{job.pay}</b><span>星币{job.paid ? " · 已入账" : " · 尚未入账"}</span></div></Card>)}</div> : <EmptyState icon="bookmark" title="还没有工作记录">TA 还没有开始一份已记录的工作。</EmptyState>}</section>
    <section><div className="ps-life-section-title"><span>02 / 身份与旅途证件</span><span>由星球签发</span></div>{credentials.isPending ? <LoadingState label="正在读取证件…" /> : credentials.isError ? <ErrorState error={credentials.error} onRetry={() => void credentials.refetch()} /> : credentials.data?.length ? <div className="ps-life-credentials">{credentials.data.map((credential: CredentialSummary) => credential.credential_id ? <Link className="ps-life-credential" to={`/credentials/${encodeURIComponent(credential.credential_id)}`} key={`${credential.kind}-${credential.credential_id}`}><span className="ps-life-credential__mark">✦</span><span><small>{STATUS[credential.status] ?? credential.status}</small><strong>{credential.label}</strong><em>{credential.number ?? "编号未签发"}</em></span><b>↗</b></Link> : <div className="ps-life-credential ps-life-credential--locked" key={credential.kind}><span className="ps-life-credential__mark">○</span><span><small>{STATUS[credential.status] ?? credential.status}</small><strong>{credential.label}</strong><em>{credential.condition}</em></span></div>)}</div> : <EmptyState icon="bookmark" title="还没有证件">等待星球签发第一张证件。</EmptyState>}</section>
    <section className="ps-life-footer"><Link to="/school">爪爪驾校 · 沿用现有课程 →</Link><p>报名和考试仍由驾校服务端裁定；这里不虚构成绩或驾照。</p></section>
  </div></Page>;
}
