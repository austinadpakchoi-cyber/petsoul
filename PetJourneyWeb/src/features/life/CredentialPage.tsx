/**
 * 单张证件（三级页，全屏）：大卡面 +“翻到背面”。正面是照片位、服务端字段（原样）、编号与签发日期；背面按种类不同。
 * 先确认这张证件在当前宠物的卡包里，才把当前宠物的照片放上去（切换宠物后不张冠李戴）。
 */
import { Link, useParams } from "react-router";
import type { CredentialDetail, CredentialLink } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { Button, DataOriginBadge, EmptyState, ErrorState, LoadingState, Page, TopBar } from "@/shared/ui";
import { dayText, formOf, linkKindText, linkRoute, statusText } from "./copy";
import { useCredentialDetail, useCredentialList, useFlip, useWalletPet, type WalletPet } from "./data";
import { CredentialBack, CredentialFront, flipHint } from "./faces";
import { LicenseUse } from "./LicenseUse";
import "./life.css";

export function CredentialPage() {
  const { credentialId } = useParams();
  const pet = useWalletPet();
  const list = useCredentialList();
  const detail = useCredentialDetail(credentialId);
  const summary = list.data?.find((item) => item.credential_id === credentialId) ?? null;
  const shown = detail.data?.summary ?? summary;
  // 副标题只放一个短状态（已使用 / 待出发 / 在途……）；行程本身就在票面上，不塞进顶栏被截断。
  const subtitle = shown ? statusText(shown) : null;

  let body;
  if (list.isPending || !pet.ready) body = <LoadingState label="正在翻开这张证件…" lines={2} />;
  else if (list.isError) body = <ErrorState error={list.error} onRetry={() => void list.refetch()} />;
  else if (!summary)
    body = (
      <EmptyState
        icon="lock"
        title={`这张证件不在${pet.name}的卡包里`}
        action={
          <Link className="ps-btn ps-btn--secondary" to="/life">
            回到卡包
          </Link>
        }
      >
        如果它属于家里另一只伙伴，先切换到那只伙伴再看。
      </EmptyState>
    );
  else if (detail.isPending) body = <LoadingState label="正在翻开这张证件…" lines={2} />;
  else if (detail.isError) body = <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />;
  else body = <CredentialView key={credentialId} detail={detail.data} pet={pet} />;

  return (
    <Page bare className="ps-cred-page">
      <TopBar title={shown?.label ?? "证件"} subtitle={subtitle ?? undefined} back="/life" right={env.dataMode === "fixture" ? <DataOriginBadge origin="fixture" /> : undefined} />
      <div className="ps-cred-content">{body}</div>
    </Page>
  );
}

function CredentialView({ detail, pet }: { detail: CredentialDetail; pet: WalletPet }) {
  const { face, phase, flip } = useFlip();
  const { summary } = detail;
  const hint = flipHint(summary.kind);
  return (
    <>
      <div className={`ps-cred-stage ps-cred-stage--${formOf(summary.kind)}`} data-phase={phase}>
        <div className="ps-cred-flip" id="ps-cred-face" role="group" aria-label={`${summary.label}${face === "front" ? "正面" : "背面"}`} data-face={face}>
          {face === "front" ? <CredentialFront detail={detail} pet={pet} /> : <CredentialBack detail={detail} pet={pet} />}
        </div>
      </div>
      <div className="ps-cred-actions">
        <Button variant="secondary" icon="refresh" aria-controls="ps-cred-face" onClick={flip}>
          {face === "front" ? "翻到背面" : "翻回正面"}
        </Button>
        {face === "front" && hint ? <span className="ps-cred-actions__hint">{hint}</span> : null}
      </div>
      {summary.kind === "driver_license" ? <LicenseUse petName={pet.name} /> : null}
      {summary.links.length ? <LinksSection links={summary.links} /> : null}
      <p className="ps-cred-foot">这是 PetSoul 星球里的纪念证件，不是现实中的证件或票据。</p>
    </>
  );
}

function LinksSection({ links }: { links: CredentialLink[] }) {
  return (
    <section className="ps-cred-links" aria-labelledby="ps-cred-links-title">
      <h2 id="ps-cred-links-title">相关经历</h2>
      <ul>
        {links.map((link, index) => {
          const to = linkRoute(link);
          const meta = [linkKindText(link.kind), dayText(link.at)].filter(Boolean).join(" · ");
          return (
            <li key={`${link.kind}-${link.ref_id}-${index}`} data-testid="cred-link">
              {to ? <Link to={to}>{link.title}</Link> : <span>{link.title}</span>}
              {meta ? <small>{meta}</small> : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
