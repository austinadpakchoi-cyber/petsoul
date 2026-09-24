/**
 * 五种内容类型共用一份正文编辑器：新建草稿与改草稿用的是同一段代码、同一套字段白名单。
 *
 * 界面只呈现**可发布**的字段；不可发布的字段单独列出来并说明原因，而不是悄悄不显示——
 * 运营看到"产量改不了"和看不到产量这一项，是两件事。
 */
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AssetListView, AssetView, ContentType, ContentTypeInfo } from "../api/types";
import { FieldName, useTech } from "../labels";
import { Pill } from "./ui";

export type Body = Record<string, unknown>;

export const EMPTY_BODY: Record<ContentType, Body> = {
  announcement: { title: "", body: "", severity: "notice", audience: "all", link: null, image_asset_id: null },
  adventure: { title: "", badge: "", story: "" },
  crop: { label: "", unit_value: 2, grow_seconds: 180 },
  job: { label: "", pay: 16, hours: 2 },
  resident: { personality: "", dream: "", source_note: null },
  destination: { title: "", city: "", summary: "", fee: 8 },
};

interface Props {
  contentType: ContentType;
  body: Body;
  disabled?: boolean;
  info?: ContentTypeInfo;
  onChange: (key: string, value: unknown) => void;
}

const text = (value: unknown) => (typeof value === "string" ? value : value == null ? "" : String(value));
const num = (value: unknown, fallback: number) => (typeof value === "number" ? value : fallback);

export function BlockedFields({ info }: { info?: ContentTypeInfo }) {
  if (!info || info.blocked.length === 0) return null;
  return (
    <div className="note plain">
      <strong>不可发布：</strong>
      {info.blocked.map((field) => <Pill key={field} tone="muted"><FieldName field={field} /></Pill>)}
      <div style={{ marginTop: 4 }}>
        这些字段会被进行中的事实实时读到，或属于身份/世界规则。改它们不是文案调整，所以运营改不了。
      </div>
    </div>
  );
}

export default function ContentBodyForm({ contentType, body, disabled, info, onChange }: Props) {
  if (contentType === "announcement") {
    return (
      <>
        <div className="field"><label>标题</label>
          <input value={text(body.title)} disabled={disabled} onChange={(e) => onChange("title", e.target.value)} /></div>
        <div className="field"><label>正文（纯文本，不接受 HTML）</label>
          <textarea value={text(body.body)} disabled={disabled} onChange={(e) => onChange("body", e.target.value)} /></div>
        <div className="row">
          <div><label>级别</label>
            <select value={text(body.severity) || "notice"} disabled={disabled} onChange={(e) => onChange("severity", e.target.value)}>
              <option value="info">一般</option><option value="notice">通知</option><option value="maintenance">维护</option>
            </select></div>
          <div><label>可见范围</label>
            <select value={text(body.audience) || "all"} disabled={disabled} onChange={(e) => onChange("audience", e.target.value)}>
              <option value="all">所有访客</option><option value="signed_in">仅已登录</option>
            </select></div>
        </div>
        <AssetPicker value={text(body.image_asset_id) || null} disabled={disabled}
                     onChange={(value) => onChange("image_asset_id", value)} />
      </>
    );
  }

  if (contentType === "destination") {
    return (
      <>
        <div className="field"><label>站名</label>
          <input value={text(body.title)} disabled={disabled} onChange={(e) => onChange("title", e.target.value)} /></div>
        <div className="row">
          <div><label>城市</label>
            <input value={text(body.city)} disabled={disabled} onChange={(e) => onChange("city", e.target.value)} /></div>
          <div><label>旅费（星币，0–300）</label>
            <input type="number" min={0} max={300} value={num(body.fee, 0)} disabled={disabled}
                   onChange={(e) => onChange("fee", Number(e.target.value))} /></div>
        </div>
        <div className="field"><label>一句话介绍</label>
          <textarea value={text(body.summary)} disabled={disabled} onChange={(e) => onChange("summary", e.target.value)} /></div>
        <div className="note plain">
          出发那一刻站名、城市与旅费就写进这趟行程了，所以改它只影响<strong>此后新出发</strong>的；
          已经在路上的那些不会被补收差价，也不会改名。
        </div>
        <BlockedFields info={info} />
      </>
    );
  }

  if (contentType === "adventure") {
    return (
      <>
        <div className="field"><label>活动标题</label>
          <input value={text(body.title)} disabled={disabled} onChange={(e) => onChange("title", e.target.value)} /></div>
        <div className="field"><label>勋章名</label>
          <input value={text(body.badge)} disabled={disabled} onChange={(e) => onChange("badge", e.target.value)} /></div>
        <div className="field"><label>故事（只能用 {"{pet}"} 与 {"{keepsake}"} 两个占位符）</label>
          <textarea value={text(body.story)} disabled={disabled} onChange={(e) => onChange("story", e.target.value)} /></div>
        <BlockedFields info={info} />
      </>
    );
  }

  if (contentType === "crop") {
    return (
      <>
        <div className="field"><label>展示名</label>
          <input value={text(body.label)} disabled={disabled} onChange={(e) => onChange("label", e.target.value)} /></div>
        <div className="row">
          <div><label>杂货铺收购价（星币 / 单位，1–50）</label>
            <input type="number" min={1} max={50} value={num(body.unit_value, 1)} disabled={disabled}
                   onChange={(e) => onChange("unit_value", Number(e.target.value))} /></div>
          <div><label>成熟用时（秒，30–86400）</label>
            <input type="number" min={30} max={86400} value={num(body.grow_seconds, 180)} disabled={disabled}
                   onChange={(e) => onChange("grow_seconds", Number(e.target.value))} /></div>
        </div>
        <div className="note plain">
          成熟用时只在<strong>种下那一刻</strong>读，改了不影响已经种下的批次；收购价是"此刻的价"，已完成的买卖记在账本里。
        </div>
        <BlockedFields info={info} />
      </>
    );
  }

  if (contentType === "job") {
    return (
      <>
        <div className="field"><label>岗位名</label>
          <input value={text(body.label)} disabled={disabled} onChange={(e) => onChange("label", e.target.value)} /></div>
        <div className="row">
          <div><label>工钱（星币，1–200）</label>
            <input type="number" min={1} max={200} value={num(body.pay, 1)} disabled={disabled}
                   onChange={(e) => onChange("pay", Number(e.target.value))} /></div>
          <div><label>工时（小时，1–12）</label>
            <input type="number" min={1} max={12} value={num(body.hours, 1)} disabled={disabled}
                   onChange={(e) => onChange("hours", Number(e.target.value))} /></div>
        </div>
        <div className="note plain">
          工钱在打工事件<strong>发生时</strong>写进事件数据并入账，所以改它只影响此后新发生的打工，已结算的工资一分不动。
        </div>
        <BlockedFields info={info} />
      </>
    );
  }

  return (
    <>
      <div className="field"><label>性格</label>
        <input value={text(body.personality)} disabled={disabled} onChange={(e) => onChange("personality", e.target.value)} /></div>
      <div className="field"><label>梦想</label>
        <input value={text(body.dream)} disabled={disabled} onChange={(e) => onChange("dream", e.target.value)} /></div>
      <div className="field"><label>来源说明（选填）</label>
        <input value={text(body.source_note)} disabled={disabled}
               onChange={(e) => onChange("source_note", e.target.value || null)} /></div>
      <div className="note plain">
        只能改<strong>还没被领养</strong>的居民。领养之后身份与经历必须连续，那时这条内容就发不出去了。
      </div>
      <BlockedFields info={info} />
    </>
  );
}


/** 公告配图：**只能从素材库里选**，填不了任意 URL——服务器也不会去抓任何外链图。 */
function AssetPicker({ value, disabled, onChange }: { value: string | null; disabled?: boolean; onChange: (v: string | null) => void }) {
  const [assets, setAssets] = useState<AssetView[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.get<AssetListView>("/assets?usage_scope=public&limit=200")
      .then((payload) => { if (alive) setAssets(payload.assets); })
      .catch(() => { if (alive) setError("读不到素材库（可能是没有「看素材库」权限）。"); });
    return () => { alive = false; };
  }, []);

  const picked = assets?.find((a) => a.asset_id === value) ?? null;
  const { on: tech } = useTech();
  return (
    <div className="field">
      <label>配图（选填，只能从素材库里选）</label>
      {error ? <div className="note plain">{error}</div> : assets === null ? <div className="empty">读取中…</div> : (
        <div className="row" style={{ alignItems: "center" }}>
          <select value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value || null)}>
            <option value="">不配图</option>
            {assets.map((asset) => (
              <option key={asset.asset_id} value={asset.asset_id}>{asset.filename}{tech ? `（${asset.asset_id}）` : ""}</option>
            ))}
          </select>
          {picked && picked.has_thumbnail && (
            <img src={`/api/v1/admin/assets/${picked.asset_id}/file?thumb=true`} alt={picked.filename}
                 style={{ flex: "0 0 auto", width: 56, height: 56, objectFit: "contain",
                          border: "1px solid var(--line)", borderRadius: 6 }} />
          )}
        </div>
      )}
      {assets !== null && assets.length === 0 && (
        <div style={{ color: "var(--ink-faint)", fontSize: 12, marginTop: 4 }}>素材库里还没有公开素材，先去素材库上传一张。</div>
      )}
    </div>
  );
}
