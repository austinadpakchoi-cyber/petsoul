/**
 * /school/ceremony（全屏，带顶栏返回）：领证仪式——龟教练盖爪印章，TA 接过证件，你们合影。
 * 打开只读状态；主人按“开始领证”才真正领证。第一次会留下一张“领证合影”收藏：开启了“生成照片”时是一张写实合影（会用到生图），
 * 否则是一张纸质纪念卡。这一步确认一直保留，页面不会自己领证，也没有别的直接触发生图的按钮；再次打开只是回看。
 * 领完说清东西在哪：驾照在证件卡包，借车券和合影在“明信片与小收藏”。主要去处固定在页面底部，首屏就看得到。
 * 素材（UI-ASSET-009）：确认页的龟教练举着空白卡、驾照正面底图、纪念卡里的教练头像；加载失败都退回原来的画法。
 */
import { useState, type ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router";
import type { CeremonyResult, CollectionItem, CredentialSummary } from "@/shared/contracts";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { useServices } from "@/shared/services/registry";
import { WorldGate } from "@/features/world_map/WorldGate";
import { Button, Card, Chip, DataOriginBadge, LoadingState, Page, PawMark, PetAvatar, TopBar } from "@/shared/ui";
import { SCHOOL_ART } from "../assets";
import { useInvalidateSchool, usePet, useSchoolPetId, useSchoolStatus } from "../hooks";
import { formatClock } from "../text";

/** 素材图：只作装饰（alt=""，旁边的文字已经说了是谁）；加载失败就换回原来的画法（fallback，没有就什么都不画）。 */
function Art({ src, width, height, className, fallback = null }: { src: string; width: number; height: number; className?: string; fallback?: ReactNode }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <>{fallback}</>;
  return <img className={className} src={src} alt="" width={width} height={height} decoding="async" onError={() => setFailed(true)} />;
}

/** 领完证去卡包看驾照：live 直达那一张；演示数据的卡包里没有这本演示驾照，去卡包首页。 */
function licenseHref(license: CredentialSummary): string {
  return env.dataMode === "live" && license.credential_id ? `/credentials/${encodeURIComponent(license.credential_id)}` : "/life";
}

function PawStamp() {
  return (
    <svg className="ds-stamp" viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="29" className="ds-stamp__ring" />
      <ellipse cx="32" cy="38" rx="10" ry="8" className="ds-stamp__pad" />
      <circle cx="20" cy="26" r="4.5" className="ds-stamp__pad" />
      <circle cx="28" cy="20" r="4.5" className="ds-stamp__pad" />
      <circle cx="37" cy="20" r="4.5" className="ds-stamp__pad" />
      <circle cx="45" cy="26" r="4.5" className="ds-stamp__pad" />
    </svg>
  );
}

/**
 * 龟教练·慢慢的线稿（占位，等 UI-ASSET-009）。与收藏页的领证纪念卡（collection/PaperMemento.tsx）同一张图：
 * 路径逐字照抄那边第 75–78 行起的几笔，两边长得一样；素材到了两边都只换这一处。两边不互相引用。
 */
function CoachTurtle() {
  return (
    <svg className="ds-memento__turtle" viewBox="0 0 48 36" width={46} height={34} fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path className="ds-memento__shell" d="M9 25C9 15 16.5 9 25 9s16 6 16 16z" />
      <path d="M20 15.5l5-2.5 5 2.5v5l-5 2.5-5-2.5zM25 9v4M20 15.5l-6-2M30 15.5l6-2M20 20.5l-7.5 4.5M30 20.5l7.5 4.5" />
      <path d="M6.5 25h37M9 25l-4.5 2M13 25.5v4.5h4v-4.5M33 25.5v4.5h4v-4.5" />
      <circle cx="44" cy="20" r="3.6" />
      <path d="M41 23.2c1.2 1 2.4 1.6 3.6 1.6" />
      <circle cx="45.2" cy="19.2" r=".5" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** 纪念卡右下角的爪印章：双圈加一枚爪印，印泥色，歪 -12°（与收藏页同款）。只是装饰。 */
function MementoStamp() {
  return (
    <svg className="ds-memento__stamp" viewBox="0 0 48 48" width={44} height={44} aria-hidden="true" focusable="false">
      <circle cx="24" cy="24" r="21.5" fill="none" stroke="currentColor" strokeWidth={2} />
      <circle cx="24" cy="24" r="17.5" fill="none" stroke="currentColor" strokeWidth={1} strokeDasharray="2.5 2" />
      <g fill="currentColor" transform="translate(12 11)">
        <circle cx="5.3" cy="9" r="2.1" />
        <circle cx="9.7" cy="5" r="2.2" />
        <circle cx="14.3" cy="5" r="2.2" />
        <circle cx="18.7" cy="9" r="2.1" />
        <path d="M12 10.8c-2.9 0-5.6 3-5.6 5.4 0 1.7 1.3 2.8 2.9 2.8 1.1 0 1.8-.5 2.7-.5s1.6.5 2.7.5c1.6 0 2.9-1.1 2.9-2.8 0-2.4-2.7-5.4-5.6-5.4z" />
      </g>
    </svg>
  );
}

const DAY = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric" });
function dayOf(iso: string | null | undefined): string | null {
  const ms = iso ? Date.parse(iso) : Number.NaN;
  return Number.isFinite(ms) ? DAY.format(ms) : null;
}

/** 照片还没换上来时底下那一行；没开“生成照片”（状态为空）时不写——纸质卡本身就是这张纪念，不是缺图。 */
const PHOTO_NOTE: Partial<Record<string, string>> = {
  processing: "合影照片还在冲洗，洗好了会换上",
  failed: "合影照片没有生成成功，留下这张纸质纪念卡",
  unknown: "合影照片的状态还没确认",
};

/** 有照片（生成好了）才算“用照片”。 */
function photoOf(memento: CollectionItem | null): string | null {
  return memento?.image_url && (memento.image_status ?? "ready") === "ready" ? memento.image_url : null;
}

/**
 * 领证合影：有照片就放照片并标明是 AI 生成的纪念合影；没有照片时是一张画出内容的纸质纪念卡（与收藏页同一设计）——
 * TA 的头像（没照片时是爪印）和龟教练并排、TA 的话（服务端原文）、领证日期、爪印章，不再是一块只写四个字的空色块。
 */
function Keepsake({ memento, words, issuedAt }: { memento: CollectionItem | null; words: string; issuedAt: string | null }) {
  const { pet, name } = usePet();
  const photo = photoOf(memento);
  if (photo && memento) {
    return (
      <Card paper className="ds-photo" data-testid="ds-keepsake">
        <figure className="ds-photo__figure">
          <img src={photo} alt={`${name}和你的领证合影`} />
          <figcaption>AI 生成的领证纪念合影，不是真实照片</figcaption>
        </figure>
        <div className="ds-photo__caption">
          <strong>领证合影</strong>
          <span className="ps-muted">{formatClock(memento.obtained_at)}</span>
          <DataOriginBadge origin={memento.data_origin} />
        </div>
      </Card>
    );
  }
  const quote = memento?.note?.trim() || words.trim();
  const day = dayOf(memento?.obtained_at ?? issuedAt);
  const status = memento?.image_status ? PHOTO_NOTE[memento.image_status] ?? null : null;
  return (
    <figure className="ds-photo ds-memento" data-testid="ds-keepsake" aria-label={`${name}和龟教练·慢慢的领证纪念卡`}>
      <div className="ds-memento__scene">
        <span className="ds-memento__who">
          {pet ? (
            <PetAvatar petId={pet.pet_id} name={name} species={pet.species} photoUrl={pet.photo_url} size={64} />
          ) : (
            <span className="ps-avatar is-placeholder" style={{ width: 64, height: 64 }} role="img" aria-label={`${name}，暂无照片`}>
              <PawMark size={32} />
            </span>
          )}
          <span className="ds-memento__name">{name}</span>
        </span>
        <span className="ds-memento__who">
          <span className="ds-memento__coach">
            <Art src={SCHOOL_ART.coach.portrait} width={60} height={60} fallback={<CoachTurtle />} />
          </span>
          <span className="ds-memento__name">龟教练·慢慢</span>
        </span>
      </div>
      {quote ? <blockquote className="ds-memento__quote">“{quote}”</blockquote> : null}
      <figcaption className="ds-memento__foot">
        {/* 日期与“在爪爪驾校领证”各自不拆行，窄屏时整段换到下一行 */}
        <span className="ds-memento__day">
          {day ? <span>{day}</span> : null}
          <span>{day ? " · 在爪爪驾校领证" : "在爪爪驾校领证"}</span>
        </span>
        <MementoStamp />
      </figcaption>
      {status ? <p className="ds-memento__status">{status}</p> : null}
    </figure>
  );
}

function Ceremony({ result }: { result: CeremonyResult }) {
  const { pet, name } = usePet();
  const license = result.license;
  return (
    <div className="ds-ceremony ps-stack">
      <p className="ds-ceremony__step">龟教练把证件放在桌上，“啪”地盖下爪印章。</p>
      <Card paper className="ds-license">
        {/* 驾照正面底图（名字、号码、照片都是代码叠上去的）；加载失败就是原来的纸色卡 */}
        <Art src={SCHOOL_ART.license.front} width={SCHOOL_ART.license.width} height={SCHOOL_ART.license.height} className="ds-license__art" />
        <div className="ds-license__head">
          <strong>PetSoul · 爪爪驾驶证</strong>
          <span>准驾车型 C</span>
        </div>
        <div className="ds-license__body">
          {pet ? <PetAvatar petId={pet.pet_id} name={name} species={pet.species} photoUrl={pet.photo_url} size={64} /> : null}
          <dl>
            <dt>持证</dt>
            <dd>{name}</dd>
            <dt>编号</dt>
            <dd>{license.number ?? "签发中"}</dd>
            <dt>签发</dt>
            <dd>{formatClock(license.issued_at)}</dd>
            <dt>机构</dt>
            <dd>爪爪驾校（PetSoul 星球交通局）</dd>
          </dl>
        </div>
        <PawStamp />
      </Card>
      <p className="ds-ceremony__step ds-ceremony__step--2">{name}双手接过证件，看了又看。</p>
      <Keepsake memento={result.memento} words={result.pet_says} issuedAt={license.issued_at} />
      {/* 纸质纪念卡里已经写着 TA 的话；只有放照片时才单独再说一句 */}
      {photoOf(result.memento) ? (
        <p className="ds-ceremony__line">
          {name}：“{result.pet_says}”
        </p>
      ) : null}
      {result.voucher ? (
        <Card className="ds-voucher">
          <Chip tone="sun" icon="gift">
            驾校借车券 ×1
          </Chip>
          <span>{result.voucher.note ?? "第一次自驾时借驾校的车，不用租车费（用一次）。"}</span>
        </Card>
      ) : null}
      <section aria-labelledby="ds-where-title" className="ps-card ds-where">
        <h2 id="ds-where-title" className="ds-where__title">
          领到的东西放在哪
        </h2>
        <ul className="ds-list">
          <li>爪爪驾驶证：放进了{name}的证件卡包（回忆 → 证件卡包）。</li>
          {result.voucher ? <li>驾校借车券：在“明信片与小收藏”里，第一次自己开车兜风时用。</li> : null}
          {result.memento ? <li>领证合影：收进了“明信片与小收藏”（回忆 → 明信片与小收藏）。</li> : null}
        </ul>
        <Link className="ds-link" to="/collection">
          去明信片与小收藏看看
        </Link>
      </section>
      <p className="ps-muted ds-footnote">
        爪爪驾驶证是 PetSoul 世界里的证件，不代表现实驾驶资格；签发机构为虚构；驾照绑定{name}，不能交易或转赠。有了驾照也要租车，借车券只能抵一次。
      </p>
      {/* 主要去处固定在页面底部：仪式再长，首屏也看得到 */}
      <nav className="ds-ceremony__actions" aria-label="领完证去哪">
        <Link className="ps-btn ps-btn--primary" to={licenseHref(license)}>
          去卡包看驾照
        </Link>
        <Link className="ps-btn ps-btn--secondary" to="/school">
          回驾校
        </Link>
      </nav>
    </div>
  );
}

/**
 * 全屏页（bareRoutes）不在主布局里，没有家庭上下文：用 WorldGate 套一层（与“我的”等全屏页同一个守卫），
 * 才知道当前是哪只宠物——一家有两只时，考局与领证的每条请求都要带上它（否则 409 pet_required）。
 */
export function CeremonyPage() {
  return (
    <WorldGate>
      <CeremonyBody />
    </WorldGate>
  );
}

function CeremonyBody() {
  const { driving } = useServices();
  const status = useSchoolStatus();
  const invalidate = useInvalidateSchool();
  const { name } = usePet();
  const petId = useSchoolPetId();
  // 只有主人按“开始领证”才调用（第一次会留下合影，可能用到生图）；页面打开时不调用。
  const run = useMutation({ mutationFn: () => driving.ceremony(petId), onSuccess: invalidate });
  const top = <TopBar title="领证仪式" subtitle="爪爪驾校" back="/school" />;
  if (status.isPending) {
    return (
      <Page bare className="ds-ceremony-page">
        {top}
        <LoadingState label="正在请龟教练…" />
      </Page>
    );
  }
  const data = status.data;
  return (
    <Page bare className="ds-ceremony-page">
      {top}
      {run.data ? (
        <Ceremony result={run.data} />
      ) : !data?.license ? (
        <div className="ps-stack ds-ceremony-intro">
          <h1 className="ps-h1">还不能领证</h1>
          <p className="ps-muted">四科都通过以后才能领证。</p>
          <Link className="ps-btn ps-btn--primary ps-btn--block" to="/school">
            回驾校
          </Link>
        </div>
      ) : (
        <div className="ps-stack ds-ceremony-intro">
          <Art src={SCHOOL_ART.coach.ceremony} width={112} height={112} className="ds-ceremony__coach" />
          <h1 className="ps-h1">{data.ceremony_done ? "回看领证仪式" : "四科都过了"}</h1>
          <p>{data.ceremony_done ? `再看一次${name}领证的样子。` : `龟教练已经把证件准备好，就等你陪${name}来领。`}</p>
          {data.ceremony_done ? null : (
            <p className="ps-muted">领证时会留下一张领证合影：开启了“生成照片”会是一张写实合影，没开启就是一张纸质纪念卡。</p>
          )}
          <Button variant="primary" block loading={run.isPending} onClick={() => run.mutate()}>
            {data.ceremony_done ? "回看" : "开始领证"}
          </Button>
          {run.error ? (
            <p className="ds-error" role="alert">
              {toApiError(run.error).playerMessage}
            </p>
          ) : null}
          <Link className="ps-btn ps-btn--ghost ps-btn--block" to="/school">
            {data.ceremony_done ? "回驾校" : "先不领"}
          </Link>
        </div>
      )}
    </Page>
  );
}
