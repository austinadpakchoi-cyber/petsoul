/**
 * 收藏里爪爪驾校的两样东西（docs/contracts/DRIVING-SCHOOL-v1.md §6、§9）：
 * 拿证时发的“驾校借车券”（kind car_voucher），领证仪式后的“领证合影”（kind license_photo）。
 * 两样都绑定这只宠物、不能交易（后端 web_collection keepsake：tradable=0、bound_to_pet=1）。
 * - 借车券的用途只写服务端 note 原文（web_driving/service.py 发券时写的那句），note 缺了就不写用途，不自己编。
 *   后端只返回还没用掉的（web_collection/service.py 的 items() 按 consumed_at IS NULL 过滤），
 *   所以列表里的借车券一律是“还没用”；用掉以后它就不在收藏里了。
 * - 领证合影：主人开了“生成照片”且配置了生图时才有写实照片（AI 生成，按图片状态显示）；否则是画出内容的纸质纪念卡
 *   （PaperMemento.tsx：TA 的头像、龟教练、爪印章、日期、TA 的话）。note 是 TA 领证时说的话，照原文加引号显示。
 * - 纪念卡与借车券标签上的名字、头像跟着当前这只宠物（useKeepsakePet），拿不到时写“TA”。
 * - 演示：只在整页打开时带 ?school_demo=licensed（和卡包里的驾照同一个开关，建服务时读一次）才放一张演示借车券；
 *   演示的“已拿证”还没做领证仪式，所以没有领证合影（和驾校演示一致，不编）。
 */
import { useQuery } from "@tanstack/react-query";
import type { CollectionItem } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useCurrentHousehold } from "@/shared/session/householdContext";
import { fixtureStageFromUrl } from "@/features/driving_school/service";
import { atMin } from "@/fixtures/world";
import { PaperMemento, type MementoPet } from "./PaperMemento";

/** 收藏卡片标题下那一行的说法（按 kind 取）。认不出的种类只写“纪念”，原始代码不上页面。 */
const KIND_TEXT = new Map<string, string>([
  ["postcard", "明信片"],
  ["seed", "稀有种子（可种进菜园）"],
  ["badge", "勋章"],
  ["shared_memory", "共同听看的回忆"],
  ["car_voucher", "爪爪驾校 · 还没用"],
  ["license_photo", "爪爪驾校 · 领证那天"],
]);

export function kindText(kind: string): string {
  return KIND_TEXT.get(kind) ?? "纪念";
}

/** 名字嵌进“绑定…，”这句：纯中文名（常用汉字区 U+4E00–U+9FFF，外加间隔号）紧挨着写；“TA”、英文名前面留一个空格（后面紧跟全角逗号，不再留）。 */
function inSentence(name: string): string {
  return /^[一-鿿·]+$/.test(name) ? name : ` ${name}`;
}

/** 绑定宠物的收藏底下那枚小标签：借车券是要用的券，不叫“个人纪念”，写明绑的是哪一只（拿不到名字时写“TA”）。 */
export function boundChipText(kind: string, petName = "TA"): string {
  return kind === "car_voucher" ? `绑定${inSentence(petName.trim() || "TA")}，不能交易` : "个人纪念，不可交易";
}

const NO_PET: MementoPet = { petId: null, name: "TA", species: "other", photoUrl: null };

/**
 * 纪念卡与标签上的“当前这只宠物”：live 用家庭上下文里当前这一只（马上就有，不多发请求）；
 * 演示没有家庭上下文，用演示家园的样板宠物（和 useActiveHome 同一个键、同一份缓存，live 下不发）。拿不到时是“TA”。
 */
export function useKeepsakePet(): MementoPet {
  const services = useServices();
  const { pet } = useCurrentHousehold();
  const fixture = env.dataMode === "fixture";
  const demo = useQuery({
    queryKey: queryKeys.home,
    // 服务在查询函数里才取：读不到只落到这条查询的错误态，页面照常（名字退回“TA”）
    queryFn: ({ signal }) => services.world.home(pet?.pet_id ?? null, signal),
    enabled: fixture,
    staleTime: 60_000,
  });
  if (!fixture) return pet ? { petId: pet.pet_id, name: pet.name, species: pet.species, photoUrl: pet.photo_url } : NO_PET;
  const sample = demo.data?.pet;
  return sample ? { petId: sample.pet_id, name: sample.name, species: sample.species, photoUrl: sample.photo_url } : NO_PET;
}

/** 借车券：用途是服务端 note 原文；没有 note 就不写。 */
export function VoucherUse({ item }: { item: CollectionItem }) {
  const note = item.note?.trim();
  if (!note) return null;
  return (
    <div className="ps-voucher-use" data-testid="voucher-use">
      <span className="ps-voucher-use__label">怎么用</span>
      <p>{note}</p>
    </div>
  );
}

/** 领证合影：照片画好了才显示照片（标 AI 生成），TA 的话照原文写在下面；否则就是那张画出内容的纸质纪念卡（话写在卡里）。 */
export function LicenseMemento({ item, pet }: { item: CollectionItem; pet: MementoPet }) {
  const photo = item.image_status === "ready" && item.image_url ? item.image_url : null;
  const note = item.note?.trim();
  if (!photo) return <PaperMemento item={item} pet={pet} />;
  return (
    <>
      <figure className="ps-collection-item__image" data-testid="license-photo">
        <img src={photo} alt={`${pet.name}和你的领证合影`} loading="lazy" />
        <figcaption>AI 生成的纪念合影，不是真实照片</figcaption>
      </figure>
      {note ? <p className="ps-collection-item__note">“{note}”</p> : null}
    </>
  );
}

/** 后端发券时写的用途（web_driving/service.py _grant_license），演示券照抄，不另写一句。 */
const DEMO_VOUCHER_NOTE = "第一次自己开车兜风时，借驾校的车，不用租车费（用一次）";

/** 演示收藏里的驾校物品：只有 ?school_demo=licensed 时才有一张借车券（和卡包演示驾照同一天签发）。 */
export function schoolDemoKeepsakes(stage = fixtureStageFromUrl()): CollectionItem[] {
  if (stage !== "licensed") return [];
  return [
    {
      item_id: "fx-voucher-1",
      kind: "car_voucher",
      item_key: null,
      title: "驾校借车券",
      obtained_at: atMin(-3 * 24 * 60),
      tradable: false,
      bound_to_pet: true,
      source_event_id: "license:fx-cr-license",
      data_origin: "fixture",
      note: DEMO_VOUCHER_NOTE,
    },
  ];
}
