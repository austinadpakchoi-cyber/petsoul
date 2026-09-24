import { useState } from "react";
import { api, uploadAsset } from "../api/client";
import type { AssetListView, AssetView, SessionView } from "../api/types";
import { ErrorNote, Pill, ReasonDialog, useAsync, when, type ConfirmSpec } from "../components/ui";
import { Code, PermissionName, Staff, Tech } from "../labels";

/** 素材只收这三种图（上传口 accept 与后端校验一致）；别的照原样显示。 */
const FILE_KIND: Record<string, string> = { "image/png": "PNG 图片", "image/jpeg": "JPEG 图片", "image/webp": "WebP 图片" };

const SOURCE_LABEL: Record<string, string> = {
  own_work: "自制",
  commissioned: "约稿",
  public_domain: "公有领域",
  licensed: "已获授权",
  ai_generated: "AI 生成",
};

/** 素材库：原件、缩略图、来源、使用范围、哈希。玩家参考照按哈希挡在门外。 */
export default function AssetsPage({ session }: { session: SessionView }) {
  const [includeRetired, setIncludeRetired] = useState(false);
  const { data, error, loading, reload } = useAsync(
    () => api.get<AssetListView>(`/assets?include_retired=${includeRetired}&limit=200`), [includeRetired]);
  const [uploading, setUploading] = useState(false);
  const [dialog, setDialog] = useState<ConfirmSpec | null>(null);
  const canManage = session.staff.permissions.includes("asset.manage");

  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <ErrorNote error={error} />;

  return (
    <>
      <div className="page-head">
        <h1>素材库</h1>
        <p>每一张都记原件、缩略图、来源和使用范围。玩家的宠物参考照进不来。</p>
      </div>

      <div className="card">
        <h2>规则</h2>
        <div className="card-body">
          <ul className="effects">{data!.rules.map((rule) => <li key={rule}>{rule}</li>)}</ul>
          <div className="actions">
            {canManage ? <button className="primary" onClick={() => setUploading(true)}>上传素材</button>
              : <span className="pill muted">上传需要「<PermissionName code="asset.manage" />」权限</span>}
            <label style={{ display: "inline-flex", gap: 6, alignItems: "center", marginBottom: 0 }}>
              <input type="checkbox" checked={includeRetired} style={{ width: "auto" }}
                     onChange={(e) => setIncludeRetired(e.target.checked)} />
              连已下架的一起看
            </label>
          </div>
        </div>
      </div>

      <div className="card">
        <h2>素材<small>{data!.assets.length} 张</small></h2>
        {data!.assets.length === 0 ? <div className="empty">素材库还是空的。</div> : (
          <table>
            <thead>
              <tr><th>预览</th><th>文件</th><th>来源</th><th>使用范围</th><th>查重</th><th>上传</th><th>操作</th></tr>
            </thead>
            <tbody>
              {data!.assets.map((asset) => (
                <tr key={asset.asset_id}>
                  <td>
                    {asset.has_thumbnail
                      ? <img src={`/api/v1/admin/assets/${asset.asset_id}/file?thumb=true`} alt={asset.filename}
                             style={{ width: 56, height: 56, objectFit: "contain", background: "var(--surface-alt)",
                                      border: "1px solid var(--line)", borderRadius: 6 }} />
                      : <span className="pill muted">无缩略图</span>}
                    {asset.thumb_note && <div style={{ fontSize: 11, color: "var(--ink-faint)" }}>{asset.thumb_note}</div>}
                  </td>
                  <td>
                    {asset.filename}
                    <Code value={asset.asset_id} />
                    <div style={{ fontSize: 12, color: "var(--ink-soft)" }}>
                      {FILE_KIND[asset.content_type] ?? asset.content_type} · {(asset.byte_size / 1024).toFixed(1)} KB<Code value={asset.content_type} />
                      {asset.width && asset.height ? ` · ${asset.width}×${asset.height}` : ""}
                    </div>
                  </td>
                  <td>
                    <Pill tone="muted">{SOURCE_LABEL[asset.source] ?? asset.source}</Pill>
                    <div style={{ fontSize: 12, marginTop: 4 }}>{asset.source_note}</div>
                    {asset.license && <div style={{ fontSize: 12, color: "var(--ink-soft)" }}>许可：{asset.license}</div>}
                  </td>
                  <td>
                    {asset.usage_scope === "public" ? <Pill tone="ok">公开</Pill> : <Pill tone="warn">仅内部</Pill>}
                    {asset.status === "retired" && <div style={{ marginTop: 4 }}><Pill tone="danger">已下架</Pill></div>}
                    {asset.retired_reason && <div style={{ fontSize: 12 }}>{asset.retired_reason}</div>}
                  </td>
                  <td style={{ maxWidth: 140 }}><span className="hint">按内容查重</span><Tech>{asset.sha256.slice(0, 24)}…</Tech></td>
                  <td style={{ fontSize: 12 }}>
                    <div><Staff id={asset.uploaded_by} /></div>
                    <div style={{ color: "var(--ink-faint)" }}>{when(asset.uploaded_at)}</div>
                  </td>
                  <td>
                    <div className="actions">
                      <a href={`/api/v1/admin/assets/${asset.asset_id}/file`} target="_blank" rel="noreferrer">看原件</a>
                      {asset.status === "active" && canManage && (
                        <button className="danger" onClick={() => setDialog({
                          title: `下架「${asset.filename}」`, danger: true, confirmLabel: "下架",
                          effects: ["玩家侧立刻取不到这张图（公开入口会 404）。",
                                    "原件保留，作为审计依据，不做硬删除。",
                                    "还挂在已发布内容上的素材会被拒绝下架。"],
                          run: (reason, op) => api.post(`/assets/${asset.asset_id}/retire`,
                            { reason, expected_version: asset.version }, op),
                        })}>下架</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {uploading && <UploadDialog options={data!} onClose={() => setUploading(false)}
                                  onDone={() => { setUploading(false); reload(); }} />}
      {dialog && <ReasonDialog spec={dialog} onClose={() => setDialog(null)} onDone={reload} />}
    </>
  );
}

function UploadDialog({ options, onClose, onDone }: { options: AssetListView; onClose: () => void; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState("own_work");
  const [note, setNote] = useState("");
  const [licenseNote, setLicenseNote] = useState("");
  const [scope, setScope] = useState("public");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("source", source);
      form.append("source_note", note.trim());
      form.append("usage_scope", scope);
      if (licenseNote.trim()) form.append("license_note", licenseNote.trim());
      await uploadAsset(form);
      onDone();
    } catch (exc) { setError(exc); } finally { setBusy(false); }
  };

  return (
    <div className="overlay">
      <div className="dialog">
        <h2>上传素材</h2>
        <div className="dialog-body">
          <ErrorNote error={error} />
          <div className="note plain">
            只接受你本机的 JPEG / PNG / WebP，不超过 5MB。上传前会比对它是不是玩家的宠物参考照，
            命中就拒绝——那是主人的照片，不能变成公共素材。
          </div>
          <div className="field">
            <label>文件</label>
            <input type="file" accept="image/jpeg,image/png,image/webp"
                   onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
          <div className="row">
            <div><label>来源（必填）</label>
              <select value={source} onChange={(e) => setSource(e.target.value)}>
                {options.sources.map((s) => <option key={s} value={s}>{SOURCE_LABEL[s] ?? s}</option>)}
              </select></div>
            <div><label>使用范围（必填）</label>
              <select value={scope} onChange={(e) => setScope(e.target.value)}>
                <option value="public">公开（玩家能看到）</option>
                <option value="internal">仅内部</option>
              </select></div>
          </div>
          <div className="field">
            <label>来源说明（必填，至少 4 个字，会进审计）</label>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} style={{ minHeight: 60 }}
                      placeholder="例如：本批运营自制的插图 / 向某画师约稿，合同编号 XXX" />
          </div>
          <div className="field">
            <label>许可说明（选填）</label>
            <input value={licenseNote} onChange={(e) => setLicenseNote(e.target.value)} placeholder="例如：CC BY 4.0，署名要求见合同" />
          </div>
        </div>
        <div className="dialog-foot">
          <button className="ghost" onClick={onClose} disabled={busy}>取消</button>
          <button className="primary" onClick={submit} disabled={busy || !file || note.trim().length < 4}>
            {busy ? "上传中…" : "上传"}
          </button>
        </div>
      </div>
    </div>
  );
}

export type { AssetView };
