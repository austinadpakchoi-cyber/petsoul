import { useState } from "react";
import { api } from "../api/client";
import type { SessionView, StaffView } from "../api/types";
import { ErrorNote, Pill, ReasonDialog, useAsync, when, type ConfirmSpec } from "../components/ui";
import { Code, Term } from "../labels";

export default function StaffPage({ session }: { session: SessionView }) {
  const { data, error, loading, reload } = useAsync(
    () => api.get<{ staff: StaffView[]; roles: { role: string; permissions: string[] }[] }>("/staff"), []);
  const [dialog, setDialog] = useState<ConfirmSpec | null>(null);
  const [editing, setEditing] = useState<StaffView | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);

  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <ErrorNote error={error} />;

  return (
    <>
      <div className="page-head">
        <h1>员工与角色</h1>
        <p>角色只是一组权限；每个员工独立身份。改角色或停用会立刻断开对方所有会话。</p>
      </div>

      <ErrorNote error={actionError} />

      <div className="card">
        <h2>员工<small>{data!.staff.length} 人</small></h2>
        <table>
          <thead><tr><th>员工</th><th>角色</th><th>二次验证</th><th>状态</th><th>最近登录</th><th>操作</th></tr></thead>
          <tbody>
            {data!.staff.map((staff) => (
              <tr key={staff.staff_id}>
                <td>{staff.display_name}<div className="hint">登录名 {staff.username}</div><Code value={staff.staff_id} /></td>
                <td>{staff.roles.map((role) => <Pill key={role} tone="muted"><Term family="role" code={role} /></Pill>)}</td>
                <td>{staff.mfa_enabled ? <Pill tone="ok">已启用</Pill> : <Pill tone="warn">未启用</Pill>}</td>
                <td>{staff.status === "active" ? <Pill tone="ok">在职</Pill> : <Pill tone="danger">已停用</Pill>}</td>
                <td>{when(staff.last_login_at)}</td>
                <td>
                  <div className="actions">
                    <button className="ghost" onClick={() => setEditing(staff)}>改角色</button>
                    {staff.staff_id !== session.staff.staff_id && (
                      <button className={staff.status === "active" ? "danger" : ""}
                              onClick={() => setDialog({
                                title: staff.status === "active" ? `停用 ${staff.username}` : `恢复 ${staff.username}`,
                                danger: staff.status === "active",
                                confirmLabel: staff.status === "active" ? "停用" : "恢复",
                                effects: staff.status === "active"
                                  ? ["这位员工所有在用会话立刻失效，也不能再登录。", "历史操作记录保留。"]
                                  : ["这位员工可以重新登录。", "之前撤销的会话不会恢复。"],
                                run: (reason, op) => api.put(`/staff/${staff.staff_id}/status`,
                                  { status: staff.status === "active" ? "disabled" : "active", expected_version: staff.version, reason }, op),
                              })}>
                        {staff.status === "active" ? "停用" : "恢复"}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>角色与权限<small>动作级；对象与字段另有检查</small></h2>
        <table>
          <thead><tr><th>角色</th><th>权限</th></tr></thead>
          <tbody>
            {data!.roles.map((role) => (
              <tr key={role.role}>
                <td><Term family="role" code={role.role} /></td>
                <td>{role.permissions.map((p) => <Pill key={p} tone={p.includes(".read") ? "muted" : "warn"}><Term family="permission" code={p} /></Pill>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="card-body">
          <div className="note plain">
            <code>private.read</code>（看私聊、私人叮嘱原文、下载参考图）不属于任何默认角色，本批也没有开放入口。
          </div>
        </div>
      </div>

      {editing && (
        <RolesDialog staff={editing} roles={data!.roles.map((r) => r.role)}
                     onClose={() => setEditing(null)}
                     onDone={() => { setEditing(null); reload(); }}
                     onError={setActionError} />
      )}
      {dialog && <ReasonDialog spec={dialog} onClose={() => setDialog(null)} onDone={reload} />}
    </>
  );
}

function RolesDialog({ staff, roles, onClose, onDone, onError }: {
  staff: StaffView; roles: string[]; onClose: () => void; onDone: () => void; onError: (e: unknown) => void;
}) {
  const [selected, setSelected] = useState<string[]>(staff.roles);
  const [busy, setBusy] = useState(false);
  const toggle = (role: string) =>
    setSelected((current) => (current.includes(role) ? current.filter((r) => r !== role) : [...current, role]));

  return (
    <div className="overlay">
      <div className="dialog">
        <h2>改 {staff.username} 的角色</h2>
        <div className="dialog-body">
          <ul className="effects">
            <li>保存后这位员工当前所有会话立刻失效，需要重新登录。</li>
            <li>角色只是一组权限；具体对象与字段仍会逐请求检查。</li>
          </ul>
          {roles.map((role) => (
            <label key={role} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
              <input type="checkbox" checked={selected.includes(role)} onChange={() => toggle(role)} style={{ width: "auto" }} />
              <span><Term family="role" code={role} /></span>
            </label>
          ))}
        </div>
        <div className="dialog-foot">
          <button className="ghost" onClick={onClose} disabled={busy}>取消</button>
          <button className="primary" disabled={busy || selected.length === 0}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await api.put(`/staff/${staff.staff_id}/roles`, { roles: selected, expected_version: staff.version });
                      onDone();
                    } catch (exc) { onError(exc); onClose(); } finally { setBusy(false); }
                  }}>保存</button>
        </div>
      </div>
    </div>
  );
}
