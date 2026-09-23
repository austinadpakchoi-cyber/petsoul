/**
 * /school/ceremony（全屏）：领证仪式——龟教练盖爪印章，TA 接过证件，你们合影。
 * 第一次会生成一张“领证合影”收藏（开启“生成照片”且配置了生图时才有写实照片，否则是纸质纪念卡）；再次打开只是回看。
 */
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router";
import type { CeremonyResult } from "@/shared/contracts";
import { toApiError } from "@/shared/api/errors";
import { useServices } from "@/shared/services/registry";
import { Button, Card, Chip, DataOriginBadge, LoadingState, Page, PetAvatar } from "@/shared/ui";
import { useInvalidateSchool, usePet, useSchoolStatus } from "../hooks";
import { formatDateTime } from "../text";

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

function Ceremony({ result }: { result: CeremonyResult }) {
  const { pet, name } = usePet();
  const license = result.license;
  const memento = result.memento;
  return (
    <div className="ds-ceremony ps-stack">
      <p className="ds-ceremony__step">龟教练把证件放在桌上，“啪”地盖下爪印章。</p>
      <Card paper className="ds-license">
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
            <dd>{formatDateTime(license.issued_at)}</dd>
            <dt>机构</dt>
            <dd>爪爪驾校（PetSoul 星球交通局）</dd>
          </dl>
        </div>
        <PawStamp />
      </Card>
      <p className="ds-ceremony__step ds-ceremony__step--2">{name}双手接过证件，看了又看。</p>
      <Card paper className="ds-photo">
        {memento?.image_url ? <img src={memento.image_url} alt={`${name}和你的领证合影`} /> : <div className="ds-photo__paper" aria-hidden="true">领证合影</div>}
        <div className="ds-photo__caption">
          <strong>领证合影</strong>
          <span className="ps-muted">{memento ? formatDateTime(memento.obtained_at) : ""}</span>
          {memento ? <DataOriginBadge origin={memento.data_origin} /> : null}
        </div>
      </Card>
      <p className="ds-ceremony__line">
        {name}：“{result.pet_says}”
      </p>
      {result.voucher ? (
        <Card className="ds-voucher">
          <Chip tone="sun" icon="gift">
            驾校借车券 ×1
          </Chip>
          <span>{result.voucher.note ?? "第一次自驾时借驾校的车，不用租车费（用一次）。"}</span>
        </Card>
      ) : null}
      <p className="ps-muted ds-footnote">
        爪爪驾驶证是 PetSoul 世界里的证件，不代表现实驾驶资格；签发机构为虚构；驾照绑定 {name}，不能交易或转赠。有了驾照也要租车，借车券只能抵一次。
      </p>
      <div className="ps-row">
        <Link className="ps-btn ps-btn--primary" to="/journey">
          去旅途看看
        </Link>
        <Link className="ps-btn ps-btn--secondary" to="/school">
          回驾校
        </Link>
      </div>
    </div>
  );
}

export function CeremonyPage() {
  const { driving } = useServices();
  const status = useSchoolStatus();
  const invalidate = useInvalidateSchool();
  const { name } = usePet();
  const run = useMutation({ mutationFn: () => driving.ceremony(), onSuccess: invalidate });
  if (status.isPending) {
    return (
      <Page bare>
        <LoadingState label="正在请龟教练…" />
      </Page>
    );
  }
  const data = status.data;
  return (
    <Page bare className="ds-prepare">
      {run.data ? (
        <Ceremony result={run.data} />
      ) : !data?.license ? (
        <div className="ps-stack">
          <h1 className="ps-h1">领证仪式</h1>
          <p className="ps-muted">四科都通过以后才能领证。</p>
          <Link className="ps-btn ps-btn--primary ps-btn--block" to="/school">
            回驾校
          </Link>
        </div>
      ) : (
        <div className="ps-stack">
          <h1 className="ps-h1">{data.ceremony_done ? "回看领证仪式" : "领证仪式"}</h1>
          <p>四科都通过了。龟教练已经把证件准备好，就等你陪{name}来领。</p>
          <Button variant="primary" block loading={run.isPending} onClick={() => run.mutate()}>
            {data.ceremony_done ? "回看" : "开始领证"}
          </Button>
          {run.error ? (
            <p className="ds-error" role="alert">
              {toApiError(run.error).message}
            </p>
          ) : null}
          <Link className="ps-btn ps-btn--ghost ps-btn--block" to="/school">
            先不领
          </Link>
        </div>
      )}
    </Page>
  );
}
