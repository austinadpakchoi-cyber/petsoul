import { useState } from "react";
import { api } from "../api/client";
import type { SessionView } from "../api/types";
import { ErrorNote } from "../components/ui";

/** 要求 MFA 的环境里，没入册的员工会话是受限的：除了这一页什么都做不了。没有跳过入口。 */
export default function MfaPage({ session, onDone }: { session: SessionView; onDone: () => void }) {
  const [secret, setSecret] = useState<{ secret: string; otpauth_uri: string; note: string } | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      setSecret(await api.post("/auth/mfa/enroll"));
    } catch (exc) { setError(exc); } finally { setBusy(false); }
  };

  const activate = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/mfa/activate", { code: code.trim() });
      onDone();
    } catch (exc) { setError(exc); } finally { setBusy(false); }
  };

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>先启用二次验证</h1>
        <p className="sub">{session.environment} 环境要求员工启用二次验证。在完成之前，这个会话做不了任何操作。</p>
        <ErrorNote error={error} />
        {!secret ? (
          <button className="primary" onClick={start} disabled={busy} style={{ width: "100%" }}>
            {busy ? "生成中…" : "开始入册"}
          </button>
        ) : (
          <>
            <div className="note plain">
              把这个密钥加进验证器应用：<br />
              <code>{secret.secret}</code>
              <br /><br />
              <span className="mono" style={{ wordBreak: "break-all" }}>{secret.otpauth_uri}</span>
              <br /><br />{secret.note}
            </div>
            <div className="field">
              <label htmlFor="code">当前验证码</label>
              <input id="code" value={code} inputMode="numeric" maxLength={6} onChange={(e) => setCode(e.target.value)} />
            </div>
            <button className="primary" onClick={activate} disabled={busy || code.trim().length !== 6} style={{ width: "100%" }}>
              {busy ? "校验中…" : "启用"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
