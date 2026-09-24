import { useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import type { SessionView, UserDetailView } from "../api/types";
import { ErrorNote, Pill, ReasonDialog, useAsync, when, type ConfirmSpec } from "../components/ui";
import { Code, PermissionName, Tech, Term } from "../labels";
import { UserLedgerSummary } from "./UserLedgerSummary";
import { UserSocial } from "./UserSocial";

interface FreezePreview {
  user_id: string;
  current_status: string;
  current_version: number;
  active_sessions: number;
  pets: number;
  effects: string[];
}

export default function UserPage({ session }: { session: SessionView }) {
  const { userId = "" } = useParams();
  const { data, error, loading, reload } = useAsync(() => api.get<UserDetailView>(`/users/${userId}`), [userId]);
  const [dialog, setDialog] = useState<ConfirmSpec | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const can = (p: string) => session.staff.permissions.includes(p);

  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;
  const frozen = data.user.account_status === "frozen";

  const openFreeze = async () => {
    setActionError(null);
    try {
      const preview = await api.get<FreezePreview>(`/users/${userId}/freeze/preview`);
      setDialog({
        title: frozen ? `解冻账号 ${data.user.username ?? userId}` : `冻结账号 ${data.user.username ?? userId}`,
        danger: !frozen,
        confirmLabel: frozen ? "解冻" : "冻结",
        placeholder: frozen ? "例如：核实过身份，误冻，解冻" : "例如：多人举报这个账号发广告，核实属实，先冻结",
        effects: frozen
          ? ["账号可以重新登录。", "之前被撤销的会话不会自动恢复，用户要重新登录。"]
          : preview.effects,
        run: (reason, op) => api.post(`/users/${userId}/freeze`,
          { frozen: !frozen, reason, expected_version: preview.current_version }, op),
      });
    } catch (exc) { setActionError(exc); }
  };

  return (
    <>
      <div className="page-head">
        <h1>{data.user.username ?? data.user.display_name ?? userId}</h1>
        <Code value={userId} />
        {frozen && <Pill tone="danger">已冻结</Pill>}
      </div>

      <ErrorNote error={actionError} />

      <div className="grid cols-2">
        <div className="card">
          <h2>账号</h2>
          <div className="card-body">
            <dl className="kv">
              <dt>显示名</dt><dd>{data.user.display_name ?? "—"}</dd>
              <dt>注册时间</dt><dd>{when(data.user.created_at)}</dd>
              <dt>最近来过</dt><dd>{when(data.prefs.last_active_at)}</dd>
              <dt>时区</dt><dd>{data.prefs.timezone}</dd>
              <dt>照顾人的设置</dt>
              <dd>
                <Pill tone={data.prefs.model_replies ? "ok" : "muted"}>AI 回复 {data.prefs.model_replies ? "开" : "关"}</Pill>{" "}
                <Pill tone={data.prefs.generated_photos ? "ok" : "muted"}>生成照片 {data.prefs.generated_photos ? "开" : "关"}</Pill>{" "}
                <Pill tone={data.prefs.pet_messages ? "ok" : "muted"}>主动来信 {data.prefs.pet_messages ? "开" : "关"}</Pill>
              </dd>
              {data.freeze && (<><dt>冻结原因</dt><dd>{data.freeze.reason}（{when(data.freeze.changed_at)}）</dd></>)}
            </dl>
            <div className="note plain" style={{ marginTop: 12 }}>{data.redaction_note}</div>
            <div className="actions">
              {can("account.freeze") && <button className={frozen ? "primary" : "danger"} onClick={openFreeze}>{frozen ? "解冻账号" : "冻结账号"}</button>}
              {can("account.revoke_session") && (
                <button onClick={() => setDialog({
                  title: "撤销全部登录会话",
                  confirmLabel: "撤销",
                  effects: ["这个账号当前所有有效会话立刻失效。", "账号本身不冻结，用户可以重新登录。"],
                  run: (reason, op) => api.post(`/users/${userId}/revoke-sessions`, { reason }, op),
                })}>撤销登录会话</button>
              )}
              {!can("account.freeze") && <span className="pill muted">冻结要「<PermissionName code="account.freeze" />」权限</span>}
            </div>
          </div>
        </div>

        <div className="card">
          <h2>登录会话<small>{data.sessions.filter((s) => !s.revoked_at).length} 个有效</small></h2>
          {data.sessions.length === 0 ? <div className="empty">没有会话记录。</div> : (
            <table>
              <thead><tr><th>登录时间</th><th>到期</th><th>状态</th></tr></thead>
              <tbody>
                {data.sessions.map((s) => (
                  <tr key={s.session_id}>
                    <td>{when(s.created_at)}<Tech>{s.session_id.slice(0, 14)}…</Tech></td>
                    <td>{when(s.expires_at)}</td>
                    <td>{s.revoked_at ? <Pill tone="muted">已撤销</Pill> : <Pill tone="ok">有效</Pill>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {data.households.map((household) => (
        <div className="card" key={household.household_id}>
          <h2>{household.name ?? "家庭"}<Code value={household.household_id} />
            <small>这位成员的角色：{household.role === "admin" ? "家庭管理员" : "共同照顾者"}（家庭角色不带平台权限）</small></h2>
          <div className="card-body">
            <div className="grid cols-2">
              <div>
                <h3 style={{ fontSize: 13, margin: "0 0 6px" }}>家人</h3>
                <table>
                  <thead><tr><th>成员</th><th>角色</th><th>状态</th></tr></thead>
                  <tbody>
                    {household.members.map((m) => (
                      <tr key={m.user_id}>
                        <td><Link to={`/users/${m.user_id}`}>{m.username ?? m.display_name ?? m.user_id}</Link></td>
                        <td>{m.role === "admin" ? "管理员" : "照顾者"}</td>
                        <td>{m.status === "active" ? <Pill tone="ok">在家</Pill> : <Pill tone="muted">不在这个家了</Pill>}<Code value={m.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <h3 style={{ fontSize: 13, margin: "0 0 6px" }}>宠物</h3>
                <table>
                  <thead><tr><th>宠物</th><th>物种</th><th>入住</th><th>诊断</th></tr></thead>
                  <tbody>
                    {household.pets.map((pet) => (
                      <tr key={pet.pet_id}>
                        <td>{pet.name}<Code value={pet.pet_id} /></td>
                        <td><Term family="species" code={pet.species} /></td>
                        <td>{pet.home_activated ? <Pill tone="ok">已入住</Pill> : <Pill tone="warn">未入住</Pill>}</td>
                        <td><Link to={`/pets/${pet.pet_id}`}>打开宠物</Link></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            {(data.homes ?? []).filter((home) => home.household_id === household.household_id).map((home) => (
              <p key={home.home_id} className="section-note">
                <Link to={`/homes/${home.home_id}`}>看这个家里的东西</Link>：仓库、菜地、偷菜记录<Code value={home.home_id} />
              </p>
            ))}
          </div>
        </div>
      ))}

      <UserSocial userId={userId} />

      {(can("economy.read") || can("provider.read")) && <UserLedgerSummary userId={userId} />}

      <div className="card">
        <h2>这个账号上的运营操作<small>仅追加</small></h2>
        {data.recent_admin_actions.length === 0 ? <div className="empty">还没有针对这个账号的运营操作。</div> : (
          <table>
            <thead><tr><th>时间</th><th>做了什么</th><th>谁</th><th>为什么</th><th>结果</th></tr></thead>
            <tbody>
              {data.recent_admin_actions.map((entry) => (
                <tr key={entry.audit_id}>
                  <td>{when(entry.occurred_at)}</td>
                  <td>{entry.action.startsWith("denied:") ? "没有权限、被挡下的请求" : <Term family="audit_action" code={entry.action} />}</td>
                  <td>{entry.actor_username ?? "—"}</td>
                  <td>{entry.reason ?? "—"}</td>
                  <td><Pill tone={entry.status === "denied" ? "danger" : entry.status === "allowed" ? "muted" : "ok"}><Term family="audit_status" code={entry.status} /></Pill><Tech>{entry.outcome}</Tech></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {dialog && <ReasonDialog spec={dialog} onClose={() => setDialog(null)} onDone={reload} />}
    </>
  );
}
