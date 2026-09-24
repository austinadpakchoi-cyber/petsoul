/**
 * 证件卡面。每种证件一个 ps-cred--<kind> 类：底色、纹样和素材钩子（--cred-art-front / --cred-art-back）都挂在它上面（见 life.css）。
 * UI-ASSET-005 v1 已交的底图：星球居民证正反、银行卡正、驾照正反；照片位对准底图自带的照片框，字段排在底图留出的空白处。
 * 其余（银行卡背面、护照、票据、房卡、照护档案）仍是 CSS 画的简版，素材到了只换背景图。
 * 不生成二维码、条码；护照底部机读码风格的代号行只由真实数据拼出（见 Passport.tsx）；不模仿任何真实国家、航空公司、银行的证件样式。
 */
import type { CredentialDetail, CredentialKind, CredentialSummary } from "@/shared/contracts";
import { Icon } from "@/shared/ui";
import { dayText, deltaText, formOf, kindEn, splitFamilyFields, splitNote, statusText, TICKET_KINDS } from "./copy";
import type { WalletPet } from "./data";
import { Glyph, KindMark } from "./glyphs";
import { PassportBooklet, PassportDataPage } from "./Passport";
import { ExtrasLine, FictionBox, FieldGrid, IdPhoto } from "./parts";

type FaceProps = { detail: CredentialDetail; pet: WalletPet };

/* ---------- 正面 ---------- */

/**
 * 星球居民证、驾驶证：和护照资料页同一家族的排版语言（用户 2026-09-24 参考样式）——
 * 抬头条（左上角“纪念用 · 非真实证件”、PETSOUL REPUBLIC、中英证件名）+ 照片框 + 中英双语字段；颜色按各自证件区分。
 * 底图的照片框和字段区是固定比例的：字段超过 5 个时正面放前 4 个，其余排到背面（splitFamilyFields）。
 */
function FamilyCard({ detail, pet }: FaceProps) {
  const { summary, fields } = detail;
  const en = kindEn(summary.kind);
  const { front } = splitFamilyFields(fields);
  return (
    <article className={`ps-idcard ps-idcard--family ps-cred ps-cred--${summary.kind}`} data-testid="cred-front">
      <header className="ps-idcard__band ps-idcard__band--family">
        <div className="ps-idcard__bandtop">
          <FictionBox />
          <span className="ps-idcard__republic" lang="en">
            PETSOUL REPUBLIC
          </span>
        </div>
        <div className="ps-idcard__title">
          <KindMark summary={summary} fields={fields} size={18} />
          <strong>{summary.label}</strong>
          {en ? <small lang="en">{en}</small> : null}
        </div>
      </header>
      <IdPhoto pet={pet} className="ps-idcard__photo" />
      <div className="ps-idcard__fields">
        <FieldGrid fields={front} bilingual />
      </div>
      <footer className="ps-idcard__foot">
        <ExtrasLine summary={summary} fields={fields} />
      </footer>
    </article>
  );
}

/**
 * 银行卡、房卡：简单卡面。银行卡底图左侧是芯片和叶子（没有照片框），TA 的证件照改放在标题条右侧的小圆框里，不盖住芯片。
 */
function CardFront({ detail, pet }: FaceProps) {
  const { summary, fields } = detail;
  const bank = summary.kind === "bank_card";
  return (
    <article className={`ps-idcard ps-cred ps-cred--${summary.kind}`} data-testid="cred-front">
      <header className="ps-idcard__band">
        <span className="ps-idcard__label">
          <KindMark summary={summary} fields={fields} size={18} />
          {summary.label}
        </span>
        {bank ? <IdPhoto pet={pet} className="ps-idcard__bandphoto" /> : <span className="ps-idcard__brand">PetSoul 星球</span>}
      </header>
      {bank ? null : <IdPhoto pet={pet} className="ps-idcard__photo" />}
      <div className="ps-idcard__fields">
        <FieldGrid fields={fields} />
      </div>
      <footer className="ps-idcard__foot">
        <ExtrasLine summary={summary} fields={fields} />
      </footer>
    </article>
  );
}

function TicketFront({ detail, pet }: FaceProps) {
  const { summary, fields } = detail;
  return (
    <article className={`ps-ticketcard ps-cred ps-cred--${summary.kind}`} data-testid="cred-front">
      <header className="ps-ticketcard__band">
        <span className="ps-ticketcard__label">
          <KindMark summary={summary} fields={fields} size={18} />
          {summary.label}
        </span>
        <span className="ps-ticketcard__who">
          <IdPhoto pet={pet} className="ps-ticketcard__photo" />
          <span>
            <small>旅客</small>
            <b>{pet.name}</b>
          </span>
        </span>
      </header>
      <div className="ps-ticketcard__fields">
        <FieldGrid fields={fields} layout="ticket" />
      </div>
      <div className="ps-ticketcard__stub" aria-label="票根">
        <ExtrasLine summary={summary} fields={fields} numberLabel="票号" />
      </div>
    </article>
  );
}

function FolderFront({ detail, pet }: FaceProps) {
  const { summary, fields } = detail;
  return (
    <article className="ps-folder ps-cred ps-cred--care_profile" data-testid="cred-front">
      <header className="ps-folder__tab">
        <KindMark summary={summary} size={16} />
        {summary.label}
      </header>
      {summary.private ? (
        <p className="ps-folder__private">
          <Icon name="lock" size={13} />
          私密 · 不会出现在公开的地方
        </p>
      ) : null}
      <IdPhoto pet={pet} className="ps-folder__photo" />
      <FieldGrid fields={fields} layout="stack" />
      <ExtrasLine summary={summary} fields={fields} />
    </article>
  );
}

export function CredentialFront({ detail, pet }: FaceProps) {
  const kind = detail.summary.kind;
  if (kind === "identity_card" || kind === "driver_license") return <FamilyCard detail={detail} pet={pet} />;
  switch (formOf(kind)) {
    case "ticket":
      return <TicketFront detail={detail} pet={pet} />;
    case "passport":
      return <PassportDataPage detail={detail} pet={pet} />;
    case "folder":
      return <FolderFront detail={detail} pet={pet} />;
    default:
      return <CardFront detail={detail} pet={pet} />;
  }
}

/* ---------- 背面 ---------- */

function BankBack({ detail }: FaceProps) {
  const { summary, balance, ledger } = detail;
  const rows = [...ledger].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  return (
    <div className="ps-bankback" data-testid="cred-back">
      <article className={`ps-idcard ps-idcard--back ps-cred ps-cred--${summary.kind}`}>
        <span className="ps-idcard__stripe" aria-hidden="true" />
        <div className="ps-bankback__balance">
          <small>余额</small>
          <strong data-testid="bank-balance">{balance == null ? "暂时看不到" : balance}</strong>
          {balance == null ? null : <span>星币</span>}
        </div>
        <p className="ps-bankback__same">和家园钱包是同一个账户</p>
      </article>
      <section className="ps-receipt" aria-labelledby="ps-receipt-title">
        <h3 id="ps-receipt-title">收支记录</h3>
        {rows.length ? (
          <ul>
            {rows.map((entry) => (
              <li key={entry.tx_id} className={entry.delta < 0 ? "is-out" : "is-in"} data-testid="ledger-row">
                <span>
                  <b>{entry.reason}</b>
                  <small>{dayText(entry.created_at)}</small>
                </span>
                <strong>{deltaText(entry.delta)}</strong>
              </li>
            ))}
          </ul>
        ) : (
          <p className="ps-receipt__empty">还没有收支记录。</p>
        )}
      </section>
    </div>
  );
}

function CareBack({ detail }: FaceProps) {
  const notes = detail.care_notes;
  return (
    <article className="ps-careback ps-cred ps-cred--care_profile" data-testid="cred-back">
      <p className="ps-careback__private" data-testid="care-private">
        <Icon name="lock" size={14} />
        <span>私密档案：这里记的是你确认过的习惯和叮嘱，只有你能看到，不会出现在公开的地方。</span>
      </p>
      {notes.length ? (
        <ol className="ps-careback__notes">
          {notes.map((note, index) => {
            const { head, body } = splitNote(note);
            return (
              <li key={`${index}-${note}`} data-testid="care-note">
                {head ? <b>{head}</b> : null}
                {body}
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="ps-careback__empty">还没有记下习惯和叮嘱。</p>
      )}
    </article>
  );
}

/** 票面带撕线票根：主票写服务端的行程标题，票根写票号与状态。 */
function TicketBack({ detail }: FaceProps) {
  const { summary, fields } = detail;
  const status = statusText(summary);
  const issued = dayText(summary.issued_at);
  return (
    <div className="ps-ticketface-wrap" data-testid="cred-back">
      <article className={`ps-ticketface ps-cred ps-cred--${summary.kind}`}>
        <div className="ps-ticketface__main">
          <span className="ps-ticketface__label">
            <KindMark summary={summary} fields={fields} size={16} />
            {summary.label}
          </span>
          <strong className="ps-ticketface__route">{summary.title ?? summary.label}</strong>
          {issued ? <small>{issued}</small> : null}
        </div>
        <div className="ps-ticketface__stub" data-testid="ticket-stub">
          <small>票根</small>
          {summary.number ? <b className="ps-mono">{summary.number}</b> : null}
          {status ? <span className={`ps-ticketface__mark${summary.status === "used" ? " is-used" : ""}`}>{status}</span> : null}
        </div>
      </article>
    </div>
  );
}

/** 背面的编号与签发日期。 */
function BackInfo({ summary }: { summary: CredentialSummary }) {
  const issued = dayText(summary.issued_at);
  return (
    <div className="ps-idcard__backinfo" data-testid="back-info">
      <span className="ps-idcard__backlabel">{summary.label}</span>
      {summary.number ? <b className="ps-mono">{summary.number}</b> : null}
      {issued ? <small>签发于 {issued}</small> : null}
    </div>
  );
}

/** 星球居民证背面：UI-ASSET-005 的海岛小镇底图（自带芯片）；编号与签发日期放在右下低对比处，正面放不下的字段也排在这里。 */
function IdentityBack({ detail }: FaceProps) {
  const { back } = splitFamilyFields(detail.fields);
  return (
    <article className="ps-idcard ps-idcard--back ps-cred ps-cred--identity_card" data-testid="cred-back">
      <div className="ps-idcard__backpanel">
        <BackInfo summary={detail.summary} />
        {back.length ? <FieldGrid fields={back} layout="stack" bilingual /> : null}
      </div>
    </article>
  );
}

/**
 * 驾驶证背面：UI-ASSET-005 的四行横线底图。正面放不下的字段按原顺序写在横线上；没有就写编号与签发日期。
 * 素材说明里提到的准驾类别图标与“是否持有”要有接口数据才画——现在接口只给“准驾车型”一个字段，不编。
 */
function LicenseBack({ detail }: FaceProps) {
  const { back } = splitFamilyFields(detail.fields);
  return (
    <article className="ps-idcard ps-idcard--back ps-idcard--ruled ps-cred ps-cred--driver_license" data-testid="cred-back">
      {back.length ? <FieldGrid fields={back} layout="ruled" bilingual /> : <BackInfo summary={detail.summary} />}
    </article>
  );
}

/** 房卡背面：磁条 + 编号与签发日期（素材未交，CSS 版）。 */
function HotelBack({ detail }: FaceProps) {
  return (
    <article className="ps-idcard ps-idcard--back ps-cred ps-cred--hotel_key" data-testid="cred-back">
      <span className="ps-idcard__stripe" aria-hidden="true" />
      <BackInfo summary={detail.summary} />
    </article>
  );
}

export function CredentialBack({ detail, pet }: FaceProps) {
  const kind = detail.summary.kind;
  if (kind === "bank_card") return <BankBack detail={detail} pet={pet} />;
  if (kind === "passport") return <PassportBooklet detail={detail} />;
  if (kind === "care_profile") return <CareBack detail={detail} pet={pet} />;
  if (TICKET_KINDS.has(kind)) return <TicketBack detail={detail} pet={pet} />;
  if (kind === "identity_card") return <IdentityBack detail={detail} pet={pet} />;
  if (kind === "driver_license") return <LicenseBack detail={detail} pet={pet} />;
  return <HotelBack detail={detail} pet={pet} />;
}

/** 翻面按钮旁的一句提示：背面有什么。 */
export function flipHint(kind: CredentialKind): string | null {
  switch (kind) {
    case "bank_card":
      return "背面是余额和收支记录";
    case "passport":
      return "背面是盖纪念章的小本";
    case "care_profile":
      return "背面是只给你看的叮嘱";
    case "boarding_pass":
    case "transport_ticket":
      return "背面是带票根的票面";
    default:
      return null;
  }
}

/* ---------- 卡包里的小卡面 ---------- */

export function MiniCard({ summary, pet }: { summary: CredentialSummary; pet: WalletPet }) {
  const form = formOf(summary.kind);
  const ticket = form === "ticket";
  const status = statusText(summary);
  const sub = ticket ? summary.title : summary.number;
  const issued = dayText(summary.issued_at);
  // 银行卡底图左侧是芯片，没有照片框：小卡面上不放照片。
  const showPhoto = !ticket && form !== "passport" && summary.kind !== "bank_card";
  return (
    <article className={`ps-mini ps-mini--${form} ps-cred ps-cred--${summary.kind}`} data-testid="wallet-card">
      <header className="ps-mini__band">
        <span className="ps-mini__mark">
          <KindMark summary={summary} size={18} />
        </span>
        <span className="ps-mini__titles">
          <strong>{summary.label}</strong>
          {sub ? <small className={ticket ? undefined : "ps-mono"}>{sub}</small> : null}
        </span>
        {summary.private ? (
          <span className="ps-mini__tag">
            <Icon name="lock" size={12} />
            私密
          </span>
        ) : status ? (
          <span className="ps-mini__tag">{status}</span>
        ) : null}
      </header>
      <div className="ps-mini__body">
        {ticket ? (
          <div className="ps-mini__ticketinfo">
            <p className="ps-mini__route">{summary.title ?? summary.label}</p>
            {issued ? <span className="ps-mini__issued">签发于 {issued}</span> : null}
          </div>
        ) : form === "passport" ? (
          <span className="ps-mini__emblem" aria-hidden="true">
            <Glyph name="globe" size={44} />
            <Glyph name="paw" size={14} />
          </span>
        ) : showPhoto ? (
          <IdPhoto pet={pet} className="ps-mini__photo" />
        ) : null}
        {!ticket && issued ? <span className="ps-mini__issued">签发于 {issued}</span> : null}
      </div>
    </article>
  );
}
