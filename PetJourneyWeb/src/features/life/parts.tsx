/** 各种卡面共用的小部件：证件照、服务端字段排版、编号与签发日期、“纪念用”声明框。 */
import type { ReactNode } from "react";
import type { CredentialField, CredentialSummary } from "@/shared/contracts";
import { petPortraitUrl } from "@/features/pets/PetPortrait";
import { faceExtras, fieldLabelEn, isWideField } from "./copy";
import type { WalletPet } from "./data";
import { Glyph } from "./glyphs";

type PhotoSource = Pick<WalletPet, "photoUrl" | "photoGenerated" | "idPhoto">;

/** 证件照已经生效：status 为 ready 且给了地址。后端在“有生效照 + 新一轮在画 / 失败”时仍返回 ready 和旧地址，所以证件上不会突然没照片。 */
function readyIdPhotoUrl(pet: Pick<WalletPet, "idPhoto">): string | null {
  const idPhoto = pet.idPhoto;
  return idPhoto && idPhoto.status === "ready" && idPhoto.url ? idPhoto.url : null;
}

/**
 * 证件照（用户 2026-09-24：每一只宠物都要有一张证件照，用在护照、居民证、驾照等所有证件的照片位）——所有照片位只从这里取图。
 * 规则（A 的契约 CharacterState.id_photo，主窗口已核过后端）：id_photo 是 ready 且有 url 时用它（3:4 竖幅浅蓝底）；
 * 否则退回 petPortraitUrl(photo_url)：有照片用照片；演示模式没有照片时是授权的演示小灰猫；live 没有照片时返回 null，照片位显示中性爪印占位。
 * 不用名字首字。
 */
export function credentialPhotoUrl(pet: PhotoSource): string | null {
  return readyIdPhotoUrl(pet) ?? petPortraitUrl(pet.photoUrl);
}

/** “AI 生成”角标：用上证件照时一律标（按真实照片生成的，或本身就是生成的基准照）；没用上时，照片是服务端生成的形象才标。 */
export function credentialPhotoIsAi(pet: PhotoSource): boolean {
  if (readyIdPhotoUrl(pet)) return true;
  return Boolean(credentialPhotoUrl(pet) && pet.photoUrl && pet.photoGenerated);
}

/**
 * 卡包封面的圆头像：有证件照上方裁出的 256×256 头像（id_photo.avatar_url）时用它，没有就照旧 PetPortrait(photo_url)。
 * 后端只在有已生效证件照（status 为 ready）时给 avatar_url；“宠物照片本身当证件照”那种没有裁好的头像，是 null，不拿整图冒充。
 */
export function coverAvatarUrl(pet: Pick<WalletPet, "idPhoto">): string | null {
  const idPhoto = pet.idPhoto;
  return idPhoto && idPhoto.status === "ready" && idPhoto.avatar_url ? idPhoto.avatar_url : null;
}

/** 封面头像的“AI 生成”：规则和证件照一样——用上证件照裁出的头像一律标；没用上时，照片是服务端生成的形象才标。 */
export function coverAvatarIsAi(pet: PhotoSource): boolean {
  if (coverAvatarUrl(pet)) return true;
  return Boolean(petPortraitUrl(pet.photoUrl) && pet.photoUrl && pet.photoGenerated);
}

/** 证件照片位（3:4 的头部在上：图片按顶部对齐裁切，不裁掉头）。 */
export function IdPhoto({ pet, className }: { pet: WalletPet; className?: string }) {
  const src = credentialPhotoUrl(pet);
  const generated = credentialPhotoIsAi(pet);
  const label = src ? `${pet.name}的证件照${generated ? "（AI 生成）" : ""}` : `${pet.name}，还没有证件照`;
  return (
    <span className={`ps-idphoto${src ? "" : " is-empty"}${className ? ` ${className}` : ""}`} role="img" aria-label={label} data-testid="id-photo">
      {src ? <img src={src} alt="" draggable={false} /> : <Glyph name="pawline" className="ps-idphoto__paw" />}
      {generated ? (
        <span className="ps-idphoto__tag" aria-hidden="true">
          AI 生成
        </span>
      ) : null}
    </span>
  );
}

/**
 * 服务端给的卡面字段：标签与内容原样显示，前端只决定排成几栏。
 * bilingual：同一家族证件（护照、星球居民证、驾驶证）在中文标签后加英文小字（只翻译认得的标签）。
 * renderValue：个别证件要控制值里的断行时传入（驾照“成绩”每一科包一个不换行的 span，见 faces.tsx）；字仍是服务端原文，不传就原样。
 */
export function FieldGrid({
  fields,
  layout = "grid",
  bilingual = false,
  renderValue,
}: {
  fields: CredentialField[];
  layout?: "grid" | "stack" | "ticket" | "ruled";
  bilingual?: boolean;
  renderValue?: (field: CredentialField) => ReactNode;
}) {
  if (!fields.length) return null;
  // 票面一行三栏、每栏更窄：超过 8 个字宽（中文算 2）就占两栏，日期、地名不折行。横线行（ruled）一行一个字段，不分栏。
  const wideAt = layout === "ticket" ? 8 : layout === "ruled" ? Number.POSITIVE_INFINITY : 13;
  return (
    <dl className={`ps-credfields ps-credfields--${layout}${bilingual ? " ps-credfields--bilingual" : ""}`}>
      {fields.map((field, index) => {
        const en = bilingual ? fieldLabelEn(field.label) : null;
        return (
          <div key={`${index}-${field.label}`} className={`ps-credfield${layout !== "stack" && isWideField(field, wideAt) ? " is-wide" : ""}`} data-testid="cred-field">
            <dt>
              <span data-testid="field-label">{field.label}</span>
              {en ? <small lang="en">{en}</small> : null}
            </dt>
            <dd data-testid="field-value">{renderValue ? renderValue(field) : field.value}</dd>
          </div>
        );
      })}
    </dl>
  );
}

/** 编号、签发日期：服务端字段里没有写到的才补在卡面底边。 */
export function ExtrasLine({ summary, fields, className, numberLabel = "编号" }: { summary: CredentialSummary; fields: CredentialField[]; className?: string; numberLabel?: string }) {
  const { number, issued } = faceExtras(summary, fields);
  if (!number && !issued) return null;
  return (
    <p className={`ps-face-extras${className ? ` ${className}` : ""}`} data-testid="face-extras">
      {number ? (
        <span>
          <small>{numberLabel}</small> <b className="ps-mono">{number}</b>
        </span>
      ) : null}
      {issued ? (
        <span>
          <small>签发</small> {issued}
        </span>
      ) : null}
    </p>
  );
}

/** 用户参考样式里的虚构声明框：护照、星球居民证、驾驶证左上角都保留。 */
export function FictionBox() {
  return (
    <span className="ps-fiction-box" data-testid="fiction-box">
      纪念用 · 非真实证件
    </span>
  );
}
