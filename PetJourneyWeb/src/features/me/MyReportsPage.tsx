/**
 * 我的 · 我的举报（/me/reports）：全屏页，左上角回 /me，不挂底栏（方案第 9 节），写法照 /me/dna（WorldGate 守）。
 * - 数据：social.myReports（GET /reports/mine，契约类型 MyReports；路由还没关联 response_model，逐条校验见 ./myReports.ts）。
 * - 开头放服务端给的 note 原文；每条写：举报的是一条动态还是一条评论、什么时候举报的、主人自己写的理由（像代码的不显示）、
 *   处理结果与处理时间。处理结果**只显示服务端的 message 原文**，不按 outcome 自己拼——措辞是产品口径，归后端；
 *   outcome、status 只决定样式（处理中 / 已处理的颜色）。编号（report_id、target_id）与原始代码不给玩家看，也不放进页面属性。
 * - 空：温和地说“你还没有举报过”。服务端答“还没开放”（后端没装运营后台；演示模式）→ 统一的 ErrorState 那一支
 *   “这里暂时还没开放”（能力名收在“技术信息”里），不编内容，也不说成“你还没有举报过”；别的错误 → ErrorState，可重试。
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import type { MyReports, ReportOutcomeItem } from "@/shared/contracts";
import { useServices } from "@/shared/services/registry";
import { useCurrentHousehold } from "@/shared/session/householdContext";
import { ErrorState, Icon, LoadingState, Page } from "@/shared/ui";
import { WorldGate } from "@/features/world_map/WorldGate";
import { formatWhen, isSettled, readableReason, targetLabel } from "./myReports";
import "./me.css";
import "./my-reports.css";

/** 查询键：共享键表（shared/query）不在本窗口的修改范围，先在这里定义；前缀 social 与举报所在的模块一致，按账号分键。 */
export const myReportsKey = (userId: string) => ["social", "my-reports", userId] as const;

export function MyReportsPage() {
  return (
    <WorldGate>
      <MyReportsBody />
    </WorldGate>
  );
}

function MyReportsBody() {
  const { social } = useServices();
  const { userId } = useCurrentHousehold();
  const reports = useQuery({ queryKey: myReportsKey(userId ?? "-"), queryFn: ({ signal }) => social.myReports(signal) });
  return (
    <Page bare className="ps-reports">
      <header className="ps-me-top">
        <Link className="ps-me-back" to="/me" aria-label="返回我的">
          <Icon name="back" size={20} />
        </Link>
        <h1>我的举报</h1>
      </header>
      {reports.isPending ? (
        <LoadingState lines={2} label="正在翻看你的举报…" />
      ) : reports.isError ? (
        <ErrorState error={reports.error} onRetry={() => void reports.refetch()} />
      ) : (
        <ReportList view={reports.data} />
      )}
    </Page>
  );
}

function ReportList({ view }: { view: MyReports }) {
  return (
    <>
      {view.note ? <p className="ps-reports-note">{view.note}</p> : null}
      {view.reports.length === 0 ? (
        <div className="ps-reports-empty" role="status">
          <span className="ps-reports-empty__icon" aria-hidden="true">
            <Icon name="mail" size={22} />
          </span>
          <h2>你还没有举报过</h2>
          <p>看到让你不舒服的动态或评论，可以举报；处理结果会写在这里。</p>
        </div>
      ) : (
        <ol className="ps-reports-list" aria-label="你的举报">
          {view.reports.map((report) => (
            <ReportItem key={report.report_id} report={report} />
          ))}
        </ol>
      )}
    </>
  );
}

function ReportItem({ report }: { report: ReportOutcomeItem }) {
  const when = formatWhen(report.created_at);
  const resolvedWhen = formatWhen(report.resolved_at);
  const reason = readableReason(report.reason);
  return (
    // data-settled 只决定颜色（处理中 / 已处理），代码本身不显示；结局文字只用下面的 message 原文。
    <li className="ps-report" data-settled={isSettled(report) ? "yes" : "no"}>
      <div className="ps-report__head">
        <strong>{targetLabel(report.target_kind)}</strong>
        {when ? <time dateTime={report.created_at}>{when} 举报</time> : null}
      </div>
      {reason ? <p className="ps-report__reason">你写的理由：{reason}</p> : null}
      <p className="ps-report__result">{report.message}</p>
      {resolvedWhen && report.resolved_at ? (
        <p className="ps-report__meta">
          处理于 <time dateTime={report.resolved_at}>{resolvedWhen}</time>
        </p>
      ) : null}
    </li>
  );
}
