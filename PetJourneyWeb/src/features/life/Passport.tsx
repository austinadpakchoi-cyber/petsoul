/**
 * 护照。
 * 正面是资料页，照用户 2026-09-24 给的参考样式用 CSS 逼近（素材以后由 r7k 画）：
 *   玫瑰粉 + 米白纸、细密防伪底纹；抬头条“宠物灵魂护照 / PETSOUL PASSPORT · PETSOUL REPUBLIC · 类型 / 签发国 / 护照号码”；
 *   左边大照片框，照片右上角压一枚圆章（和纪念章同一套）；右边两栏中英双语字段——只显示服务端 fields 真实给的，没有的不编；
 *   “主人签名”一栏（服务端没给签名就空着，不写假名字）；最下方两行机读码风格等宽字（只由真实数据拼出 PetSoul 自己的代号）；
 *   左上角“纪念用 · 非真实证件”。PETSOUL REPUBLIC / PSR / PETS 都是虚构的，不模仿任何真实国家。
 * 背面是可翻页的小本：封面之后是纪念章页，章按服务端的真实 stamps（城市、盖章时间）画——城市沿上弧、日期沿下弧（SVG textPath），
 *   轻微旋转，红 / 蓝 / 绿墨色按盖章先后轮换。
 */
import { useId, useState, type CSSProperties } from "react";
import type { CredentialDetail, CredentialSummary, PassportStamp } from "@/shared/contracts";
import { Button } from "@/shared/ui";
import { chunk, hashOf, passportMrz, stampDate } from "./copy";
import type { WalletPet } from "./data";
import { Glyph } from "./glyphs";
import { FictionBox, FieldGrid, IdPhoto } from "./parts";

export const STAMPS_PER_PAGE = 4;
const INKS = ["red", "blue", "green"] as const;

/** 邮戳式锯齿外圈（一次算好）。 */
const SERRATED = (() => {
  const teeth = 36;
  const points: string[] = [];
  for (let i = 0; i < teeth * 2; i += 1) {
    const angle = (Math.PI * i) / teeth;
    const radius = i % 2 === 0 ? 57 : 53.5;
    points.push(`${(60 + radius * Math.cos(angle)).toFixed(2)} ${(60 + radius * Math.sin(angle)).toFixed(2)}`);
  }
  return `M${points.join(" L")} Z`;
})();

/**
 * 一枚圆章：上弧、下弧各一行字（SVG textPath），中间一枚爪印；印泥斑驳用 feTurbulence 做。
 * 纪念章与资料页照片上的章是同一套。UI-ASSET-005 的 C 组印章遮罩到位后，外圈可换成 CSS mask。
 */
export function InkStamp({ top, bottom, seed, shape, label, testIds }: { top: string; bottom: string; seed: number; shape: number; label?: string; testIds?: { top: string; bottom: string } }) {
  const uid = `st${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  return (
    <svg viewBox="0 0 120 120" role={label ? "img" : undefined} aria-label={label || undefined} aria-hidden={label ? undefined : true}>
      <defs>
        <path id={`${uid}-top`} d="M 22 60 A 38 38 0 0 1 98 60" />
        <path id={`${uid}-bottom`} d="M 12 60 A 48 48 0 0 0 108 60" />
        <filter id={`${uid}-ink`} x="-8%" y="-8%" width="116%" height="116%">
          <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves={2} seed={seed % 97} result="noise" />
          <feColorMatrix in="noise" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -1.25 1.38" result="speckle" />
          <feComposite in="SourceGraphic" in2="speckle" operator="in" />
        </filter>
      </defs>
      <g filter={`url(#${uid}-ink)`}>
        {shape === 1 ? (
          <path d={SERRATED} fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinejoin="round" />
        ) : (
          <circle cx="60" cy="60" r="55" fill="none" stroke="currentColor" strokeWidth={shape === 2 ? 5 : 3} />
        )}
        <circle cx="60" cy="60" r="35" fill="none" stroke="currentColor" strokeWidth={1.4} strokeDasharray={shape === 0 ? "2.5 3" : undefined} />
        <text className="ps-stamp__city" data-testid={testIds?.top}>
          <textPath href={`#${uid}-top`} startOffset="50%" textAnchor="middle">
            {top}
          </textPath>
        </text>
        <text className="ps-stamp__date" data-testid={testIds?.bottom}>
          <textPath href={`#${uid}-bottom`} startOffset="50%" textAnchor="middle">
            {bottom}
          </textPath>
        </text>
        <g transform="translate(46.5 46.5) scale(1.125)" fill="currentColor">
          <circle cx="6.3" cy="10" r="2.1" />
          <circle cx="9.7" cy="6" r="2.2" />
          <circle cx="14.3" cy="6" r="2.2" />
          <circle cx="17.7" cy="10" r="2.1" />
          <path d="M12 11.8c-2.9 0-5.6 3-5.6 5.4 0 1.7 1.3 2.8 2.9 2.8 1.1 0 1.8-.5 2.7-.5s1.6.5 2.7.5c1.6 0 2.9-1.1 2.9-2.8 0-2.4-2.7-5.4-5.6-5.4z" />
        </g>
      </g>
    </svg>
  );
}

export function PassportDataPage({ detail, pet }: { detail: CredentialDetail; pet: WalletPet }) {
  const { summary, fields } = detail;
  // 护照号按参考样式放进抬头条（标签仍用服务端原文）；其余字段照服务端顺序排进正文两栏。
  const numberField = summary.number ? (fields.find((field) => field.value.trim() === summary.number) ?? null) : null;
  const bodyFields = numberField ? fields.filter((field) => field !== numberField) : fields;
  const place = fields.find((field) => field.label.trim() === "签发地")?.value.trim() || "PETSOUL";
  const issued = summary.issued_at ? stampDate(summary.issued_at) : "";
  const mrz = passportMrz(summary, pet.species);
  return (
    <article className="ps-passport-data ps-cred ps-cred--passport" data-testid="cred-front">
      <FictionBox />
      <header className="ps-passport-data__head">
        <div className="ps-passport-data__title">
          <strong>宠物灵魂护照</strong>
          <small lang="en">PETSOUL PASSPORT</small>
        </div>
        <div className="ps-passport-data__republic" lang="en">
          PETSOUL REPUBLIC
        </div>
        <dl className="ps-passport-data__meta">
          <div>
            <dt>
              类型 <small lang="en">Type</small>
            </dt>
            <dd>PETS</dd>
          </div>
          <div>
            <dt>
              签发国 <small lang="en">Code</small>
            </dt>
            <dd>PSR</dd>
          </div>
          {summary.number ? (
            <div className="is-number" data-testid="passport-number">
              <dt>
                {numberField?.label ?? "护照号码"} <small lang="en">Passport No.</small>
              </dt>
              <dd className="ps-mono">{summary.number}</dd>
            </div>
          ) : null}
        </dl>
      </header>
      <div className="ps-passport-data__body">
        <div className="ps-passport-data__photo">
          <IdPhoto pet={pet} />
          {issued ? (
            <span className="ps-passport-data__seal ps-stamp--red" aria-hidden="true">
              <InkStamp top={place} bottom={issued} seed={hashOf(summary.number ?? place)} shape={0} />
            </span>
          ) : null}
        </div>
        <FieldGrid fields={bodyFields} bilingual />
      </div>
      <div className="ps-passport-data__sign" data-testid="owner-signature">
        <span>
          主人签名 <small lang="en">Owner&apos;s signature</small>
        </span>
        <i aria-hidden="true" />
      </div>
      {mrz ? (
        <p className="ps-passport-data__mrz ps-mono" data-testid="passport-mrz" aria-hidden="true">
          <span>{mrz[0]}</span>
          <span>{mrz[1]}</span>
        </p>
      ) : null}
    </article>
  );
}

function PassportCover({ summary, count }: { summary: CredentialSummary; count: number }) {
  return (
    <div className="ps-passport-cover">
      <span className="ps-passport-cover__title">{summary.title ?? summary.label}</span>
      <span className="ps-passport-cover__emblem" aria-hidden="true">
        <Glyph name="globe" size={96} />
        <Glyph name="paw" size={30} />
      </span>
      <span className="ps-passport-cover__hint">{count ? `已盖 ${count} 枚纪念章，翻开看看` : "还没有纪念章，翻开看看"}</span>
    </div>
  );
}

/** 一页四个章位（占页面宽高的百分比），再按章各自的哈希微调。 */
const SLOTS = [
  { x: 5, y: 12 },
  { x: 51, y: 17 },
  { x: 8, y: 51 },
  { x: 52, y: 56 },
];

/** order 是这枚章在整本护照里按时间的序号：墨色按序号轮换（红 → 蓝 → 绿），新章只会加在后面，旧章的墨色不会变。 */
export function Stamp({ stamp, slot, order }: { stamp: PassportStamp; slot: number; order: number }) {
  const hash = hashOf(`${stamp.journey_id}|${stamp.city}|${stamp.stamped_at}`);
  const ink = INKS[order % INKS.length];
  const shape = (hash >>> 4) % 3; // 0 双圈虚线 / 1 邮戳锯齿 / 2 粗单圈
  const rotate = ((hash >>> 8) % 25) - 12;
  const base = SLOTS[slot % SLOTS.length];
  const left = base.x + (((hash >>> 12) % 7) - 3);
  const top = base.y + (((hash >>> 16) % 7) - 3);
  const date = stampDate(stamp.stamped_at);
  const style = { left: `${left}%`, top: `${top}%`, "--stamp-rotate": `${rotate}deg` } as CSSProperties;
  return (
    <figure className={`ps-stamp ps-stamp--${ink}`} style={style} data-testid="passport-stamp">
      <InkStamp top={stamp.city} bottom={date} seed={hash} shape={shape} label={`${stamp.city} 纪念章，${date}`} testIds={{ top: "stamp-city", bottom: "stamp-date" }} />
      <figcaption>{stamp.title}</figcaption>
    </figure>
  );
}

function StampPage({ stamps, index, count }: { stamps: PassportStamp[]; index: number; count: number }) {
  return (
    <div className="ps-stamp-page">
      <header className="ps-stamp-page__head">
        <span>纪念章</span>
        <small>
          {index} / {count}
        </small>
      </header>
      {stamps.length ? (
        stamps.map((stamp, slot) => (
          <Stamp key={`${stamp.journey_id}-${stamp.city}-${stamp.stamped_at}`} stamp={stamp} slot={slot} order={(index - 1) * STAMPS_PER_PAGE + slot} />
        ))
      ) : (
        <p className="ps-stamp-page__empty">还没有纪念章。TA 出远门到了目的地，会在这里盖上一枚。</p>
      )}
    </div>
  );
}

/** 背面：可翻页的小本（封面 → 纪念章页）。纪念章按盖章时间从早到晚排。 */
export function PassportBooklet({ detail }: { detail: CredentialDetail }) {
  const sorted = [...detail.stamps].sort((a, b) => Date.parse(a.stamped_at) - Date.parse(b.stamped_at));
  const stampPages = sorted.length ? chunk(sorted, STAMPS_PER_PAGE) : [[]];
  const last = stampPages.length; // 第 0 页是封面
  const [page, setPage] = useState(0);
  const [turn, setTurn] = useState<"next" | "prev" | null>(null);
  const go = (step: 1 | -1) => {
    const next = Math.min(last, Math.max(0, page + step));
    if (next === page) return;
    setTurn(step > 0 ? "next" : "prev");
    setPage(next);
  };
  return (
    <div className="ps-passport-book ps-cred ps-cred--passport" data-testid="cred-back">
      <div key={page} className={`ps-passport-book__sheet${turn ? ` is-turn-${turn}` : ""}`}>
        {page === 0 ? <PassportCover summary={detail.summary} count={sorted.length} /> : <StampPage stamps={stampPages[page - 1]} index={page} count={stampPages.length} />}
      </div>
      <nav className="ps-passport-book__nav" aria-label="护照翻页">
        <Button size="sm" variant="ghost" icon="back" disabled={page === 0} onClick={() => go(-1)}>
          上一页
        </Button>
        <span aria-live="polite">{page === 0 ? "封面" : `纪念章 ${page} / ${stampPages.length}`}</span>
        <Button size="sm" variant="ghost" disabled={page === last} onClick={() => go(1)}>
          {page === 0 ? "翻开" : "下一页"}
        </Button>
      </nav>
    </div>
  );
}
