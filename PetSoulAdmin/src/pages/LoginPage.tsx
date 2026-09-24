import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ErrorNote } from "../components/ui";

interface Meta {
  admin_version: string;
  environment: string;
  configured: boolean;
  tables_ready: boolean;
  initialized: boolean;
  require_mfa: boolean;
}

export default function LoginPage({ onSignedIn }: { onSignedIn: () => void }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [needsMfa, setNeedsMfa] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.get<Meta>("/meta").then(setMeta).catch(() => setMeta(null)); }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/login", { username, password, mfa_code: mfaCode || null });
      onSignedIn();
    } catch (exc) {
      const code = (exc as { code?: string }).code;
      if (code === "MFA_REQUIRED") setNeedsMfa(true);
      setError(exc);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1>PetSoul 运营后台</h1>
        <p className="sub">
          员工登录。这套账号与玩家账号完全分开，家庭管理员不会因此获得平台权限。
        </p>
        <ErrorNote error={error} />
        {meta && !meta.initialized && (
          <div className="note warn">
            还没有任何员工账号。第一个账号只能在服务器上创建：
            <br />
            <code>python -m app.web_admin.bootstrap --username &lt;名字&gt;</code>
            <br />网页没有创建入口，也没有恢复后门。
          </div>
        )}
        {meta && !meta.configured && <div className="note danger">这个环境没有配置会话密钥，暂时无法登录。</div>}
        <div className="field">
          <label htmlFor="u">员工名</label>
          <input id="u" value={username} autoComplete="username" onChange={(e) => setUsername(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="p">口令</label>
          <input id="p" type="password" value={password} autoComplete="current-password"
                 onChange={(e) => setPassword(e.target.value)} required />
        </div>
        {needsMfa && (
          <div className="field">
            <label htmlFor="m">二次验证码</label>
            <input id="m" value={mfaCode} inputMode="numeric" autoComplete="one-time-code"
                   onChange={(e) => setMfaCode(e.target.value)} />
          </div>
        )}
        <button className="primary" type="submit" disabled={busy} style={{ width: "100%" }}>
          {busy ? "登录中…" : "登录"}
        </button>
        {meta && (
          <p className="sub" style={{ marginTop: 14, marginBottom: 0 }}>
            环境 <strong>{meta.environment}</strong> · {meta.admin_version}
            {meta.require_mfa ? " · 本环境要求二次验证" : ""}
          </p>
        )}
      </form>
    </div>
  );
}
