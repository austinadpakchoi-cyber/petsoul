/**
 * 待领养居民：驿站里住着的伙伴、谁已经被领养。只读。
 * 客服（「我想领养的那只怎么没了」）与内容运营（居民档案）都要看：「查用户与家庭」或「看内容」任一即可；
 * 被哪位玩家领养只给有「查用户与家庭」的人（后端不给就显示说明，不猜）。
 * 居民档案（性格、梦想、来源说明）玩家在领养页也看得到；要改它走「内容发布」里的居民类型，这里不改。
 */
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import type { PetRuntimeRow, PetsRuntimeView, ResidentRow, ResidentsView, SessionView } from "../api/types";
import { pauseSpec } from "../components/runtime";
import { Player } from "../components/player";
import { ErrorNote, Pill, ReasonDialog, useAsync, when, type ConfirmSpec } from "../components/ui";
import { Code, PermissionName, Term, useFamily } from "../labels";

export default function ResidentsPage({ session }: { session: SessionView }) {
  const { data, error, loading } = useAsync(() => api.get<ResidentsView>("/residents"), []);
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const statuses = useFamily("resident_status");
  const can = (p: string) => session.staff.permissions.includes(p);
  // 运行状态（在运行 / 已暂停）来自「宠物运行」：要 pet.read；只有内容权限的人看不到这一列
  const runtime = useAsync(() => (can("pet.read") ? api.get<PetsRuntimeView>("/pets-runtime") : Promise.resolve(null)), []);
  const [dialog, setDialog] = useState<ConfirmSpec | null>(null);
  const [preview, setPreview] = useState<ResidentRow | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const running = new Map((runtime.data?.pets ?? []).map((row) => [row.pet_id, row]));
  const pauseOpen = runtime.data?.modes.pause_open ?? false;

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.residents ?? []).filter((r) => (!status || r.status === status)
      && (!q || [r.name, r.city, r.residence_label, r.pet_id].some((v) => v?.toLowerCase().includes(q))));
  }, [data, status, query]);

  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;

  return (
    <>
      <div className="page-head">
        <h1>待领养居民</h1>
        <p>{data.note}</p>
      </div>

      {data.residents === null ? <div className="card"><div className="empty">{data.note}</div></div> : (
        <>
          <div className="card">
            <div className="card-body" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
              <span>
                {Object.entries(data.counts ?? {}).map(([code, n], i) => (
                  <span key={code}>{i > 0 && " · "}<Term family="resident_status" code={code} /> {n} 只</span>))}
              </span>
              <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="按状态筛选" style={{ width: "auto" }}>
                <option value="">全部状态</option>
                {Object.entries(statuses).map(([code, text]) => <option key={code} value={code}>{text}</option>)}
              </select>
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="按名字、城市、驿站找" aria-label="按名字找"
                     style={{ width: 220 }} />
            </div>
          </div>
          {data.adopters_note && <div className="note plain">{data.adopters_note}</div>}
          <div className="actions" style={{ marginBottom: 12 }}>
            <button disabled title="要 I / A 的居民建档与形象资产入口">新增居民</button>
            <span className="hint">新增居民还没有入口：要先有 I / A 的居民建档与形象资产能力（批量建档归后台，但领域里的写入口还没有）。现在能改的是已有居民的文案（每行的「编辑档案」）。</span>
          </div>
          <div className="note plain">
            <strong>能对居民做什么：</strong>改文案走「内容发布」里的居民类型；暂停 / 恢复它的自主运行在下面每一行（要「<PermissionName code="pet.maintain" />」权限）。
            <strong>撤下（不再出现在领养名单）还没开放</strong>：玩家那一侧的领养名单与领养入口要先认「撤下」，这部分代码归总集成窗口，等排期。
            <strong>不提供删除</strong>：居民是有稳定身份和公开经历的宠物，删掉会让它的经历、钱包和别人家的记录对不上。
          </div>
          <ErrorNote error={actionError} />

          <div className="card">
            <h2>名单<small>{rows.length} 只</small></h2>
            {rows.length === 0 ? <div className="empty">没有符合条件的居民。</div> : (
              <table>
                <thead><tr><th>照片</th><th>居民</th><th>住在哪</th><th>档案</th><th>状态</th><th>被谁领养</th>{runtime.data && <th>运行</th>}</tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <Row key={r.pet_id} row={r} canPets={can("pet.read")} canUsers={can("user.read")} canEdit={can("content.edit")}
                         onPreview={() => setPreview(r)}
                         runtime={runtime.data ? running.get(r.pet_id) ?? null : undefined}
                         canPause={can("pet.maintain") && pauseOpen}
                         onPause={async () => { setActionError(null); try { setDialog(await pauseSpec(r.pet_id, r.name)); } catch (exc) { setActionError(exc); } }} />
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
      {dialog && <ReasonDialog spec={dialog} onClose={() => setDialog(null)} onDone={runtime.reload} />}
      {preview && <CardPreview row={preview} onClose={() => setPreview(null)} />}
    </>
  );
}

function Row({ row, canPets, canUsers, canEdit, runtime, canPause, onPause, onPreview }: {
  row: ResidentRow; canPets: boolean; canUsers: boolean; canEdit: boolean; runtime: PetRuntimeRow | null | undefined;
  canPause: boolean; onPause: () => void; onPreview: () => void;
}) {
  const name = row.name ?? "（没有名字）";
  return (
    <tr>
      <td><Thumb petId={row.pet_id} name={name} /></td>
      <td>
        {canPets ? <Link to={`/pets/${row.pet_id}`}>{name}</Link> : name}
        <div className="hint"><Term family="species" code={row.species} /> · <Term family="resident_kind" code={row.kind} /></div>
        <Code value={row.pet_id} />
      </td>
      <td>{row.residence_label ?? "—"}{row.city && <div className="hint">{row.city}</div>}</td>
      <td style={{ maxWidth: 320 }}>
        {row.personality && <div>性格：{row.personality}</div>}
        {row.dream && <div>梦想：{row.dream}</div>}
        {row.origin && <div className="hint">来源：<Term family="pet_origin" code={row.origin} />{row.source_note ? `（${row.source_note}）` : ""}</div>}
        {!row.personality && !row.dream && !row.origin && <span className="hint">没有档案</span>}
        <div className="actions" style={{ marginTop: 6 }}>
          {row.status === "resident" && <button className="ghost" onClick={onPreview}>预览领养卡</button>}
          {row.content_item ? <Link to={`/content/${row.content_item.item_id}`}>编辑档案（已有内容{row.content_item.live_revision ? `，线上第 ${row.content_item.live_revision} 版` : "，还没发布"}）</Link>
            : row.status === "resident" && row.candidate_id && canEdit
              ? <Link to={`/content?new=resident&slug=${encodeURIComponent(row.candidate_id)}`}>编辑档案</Link>
              : row.status === "adopted" ? <span className="hint">已被领养：身份与经历要连续，档案不再改</span> : null}
        </div>
        <div className="hint" style={{ marginTop: 4 }}>形象照片：还没有管理入口（原创居民的形象要 A 的居民资产入口）{canPets && <>，<Link to={`/pets/${row.pet_id}`}>看形象的生成状态</Link></>}</div>
      </td>
      <td>
        <Pill tone={row.status === "adopted" ? "muted" : "ok"}><Term family="resident_status" code={row.status} /></Pill>
        {row.availability && row.availability !== row.status && (
          <div className="hint" style={{ marginTop: 4 }}>领养页上：<Term family="adoption_availability" code={row.availability} /></div>)}
        {row.public_since && <div className="hint">{when(row.public_since)} 起公开</div>}
      </td>
      <td>
        {row.status !== "adopted" ? "—" : row.adopted_by ? (
          <>
            <Player id={row.adopted_by} name={row.adopted_by_name} link={canUsers} />
            <div className="hint">{when(row.adopted_at)} 领养{row.adopted_home_id && canUsers && <> · <Link to={`/homes/${row.adopted_home_id}`}>看这个家</Link></>}</div>
          </>
        ) : <span className="hint">{row.adopted_at ? `${when(row.adopted_at)} 领养` : "已领养"}</span>}
      </td>
      {runtime !== undefined && (
        <td>
          {runtime === null ? <span className="hint">没有运行记录</span> : runtime.paused ? <Pill tone="danger">已暂停</Pill> : <Pill tone="muted">在运行</Pill>}
          {runtime && (runtime.paused || (canPause && row.status === "resident")) && (
            <div className="actions" style={{ marginTop: 6 }}>
              <button className={runtime.paused ? "primary" : "ghost"} onClick={onPause}>{runtime.paused ? "恢复" : "暂停"}</button>
            </div>
          )}
        </td>
      )}
    </tr>
  );
}

/** 缩略图：只用玩家那一侧本来就公开的宠物头像；没有公开照片就写「还没有照片」（不显示参考图这类私密图片）。 */
function Thumb({ petId, name }: { petId: string; name: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <span className="hint">还没有照片</span>;
  return <img src={`/api/v1/web/public/media/pets/${encodeURIComponent(petId)}/photo`} alt={name} onError={() => setFailed(true)}
              style={{ width: 48, height: 48, objectFit: "cover", borderRadius: 8, border: "1px solid var(--line)" }} />;
}

/** 预览领养卡：玩家在领养页会看到的文字（名字、物种、性格、梦想、来源、住在哪、从什么时候开始在星球上生活）。版式以玩家端为准。 */
function CardPreview({ row, onClose }: { row: ResidentRow; onClose: () => void }) {
  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <div className="dialog">
        <h2>领养卡预览：{row.name ?? "（没有名字）"}</h2>
        <div className="dialog-body">
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <Thumb petId={row.pet_id} name={row.name ?? ""} />
            <div>
              <div style={{ fontSize: 16, fontWeight: 650 }}>{row.name ?? "（没有名字）"}</div>
              <div className="hint"><Term family="species" code={row.species} />{row.residence_label ? ` · 住在${row.residence_label}` : ""}</div>
            </div>
          </div>
          <dl className="kv" style={{ marginTop: 12 }}>
            <dt>性格</dt><dd>{row.personality ?? "—"}</dd>
            <dt>梦想</dt><dd>{row.dream ?? "—"}</dd>
            <dt>来源</dt><dd>{row.origin ? <Term family="pet_origin" code={row.origin} /> : "—"}{row.source_note ? `（${row.source_note}）` : ""}</dd>
            <dt>在星球上生活</dt><dd>{row.public_since ? `从 ${when(row.public_since)} 开始` : "—"}</dd>
          </dl>
          <p className="section-note">这是领养卡上会出现的文字，版式以玩家端为准；改文案走「内容发布」里的居民类型（这一行的「编辑档案」）。</p>
        </div>
        <div className="dialog-foot"><button className="ghost" onClick={onClose}>关闭</button></div>
      </div>
    </div>
  );
}
