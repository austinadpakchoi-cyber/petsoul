/**
 * 到站明信片（docs/coordination/ARRIVAL-SELFIE-DESIGN-2026-09-24.md）：TA 第一次住进家后寄来的那张。
 * - 认法：收藏里 kind=postcard、source_event_id 以 “arrival:” 开头（后端自然键 arrival:<pet_id>；到站消息那边来源号不外露，认不出）。
 * - 自拍（和聊天里那条“我到站啦”是同一张图）：
 *   · ready 且有地址：显示照片，说明写“{名字}到站后拍的第一张自拍（AI 生成，不是真实照片）”——不是旅行自拍，也不是到访照片；
 *   · processing：纸色的“冲洗中”占位（像一张正在显影的相纸），不像缺图；洗好了由收藏接口换成 ready，这里自动换上照片；
 *   · unknown：同一个占位，写“还没确认”——不当成失败，也不当成没有；
 *   · failed：不画占位，卡片下面一行说明，明信片本身照样在；
 *   · 空（没开生成照片 / 生图不可用）：就是一张手写明信片，不提自拍。
 * - 手写部分：TA 写的话（服务端 note 原文）、寄出地（后端给的片区与城市，原样拼）、日期、爪印邮票；纸色底、深墨字，昼夜一样。
 */
import type { CollectionItem } from "@/shared/contracts";
import { Icon } from "@/shared/ui";
import { atMin } from "@/fixtures/world";
import { PawStamp, type MementoPet } from "./PaperMemento";

export function isArrivalPostcard(item: Pick<CollectionItem, "kind" | "source_event_id">): boolean {
  return item.kind === "postcard" && typeof item.source_event_id === "string" && item.source_event_id.startsWith("arrival:");
}

const DAY = new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric" });

function dayOf(iso: string): string | null {
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? DAY.format(ms) : null;
}

/** 寄出地：后端给的城市与片区（例如“香港”“西贡的海边”）原样拼；片区里已经带着城市名时不重复。 */
function fromWhere(item: Pick<CollectionItem, "city" | "place">): string | null {
  const city = item.city?.trim();
  const place = item.place?.trim();
  if (city && place) return place.startsWith(city) ? place : `${city}·${place}`;
  return place || city || null;
}

export function ArrivalPostcard({ item, pet }: { item: CollectionItem; pet: MementoPet }) {
  const photo = item.image_status === "ready" && item.image_url ? item.image_url : null;
  const developing = !photo && (item.image_status === "processing" || item.image_status === "unknown");
  const note = item.note?.trim();
  const where = fromWhere(item);
  const day = dayOf(item.obtained_at);
  return (
    <div className="ps-arrival-postcard" data-testid="arrival-postcard">
      {photo ? (
        <figure className="ps-arrival-postcard__photo" data-testid="arrival-photo">
          <img src={photo} alt={`${pet.name}到站后拍的第一张自拍`} loading="lazy" />
          <figcaption>{pet.name}到站后拍的第一张自拍（AI 生成，不是真实照片）</figcaption>
        </figure>
      ) : developing ? (
        <div className="ps-arrival-postcard__developing" data-testid="arrival-developing">
          <span className="ps-arrival-postcard__film" aria-hidden="true">
            <Icon name="camera" size={26} />
          </span>
          <span>{item.image_status === "processing" ? "到站自拍冲洗中，洗好了会换上" : "这张到站自拍还没确认"}</span>
        </div>
      ) : null}
      <div className="ps-arrival-postcard__card" data-testid="arrival-card">
        <div className="ps-arrival-postcard__text">
          {note ? <p className="ps-arrival-postcard__note">“{note}”</p> : null}
          <p className="ps-arrival-postcard__from">
            {where ? <span>寄自 {where}</span> : <span>寄自 TA 的新家</span>}
            {day ? <span className="ps-arrival-postcard__day"> · {day}</span> : null}
          </p>
        </div>
        <PawStamp testId="arrival-stamp" />
      </div>
      {item.image_status === "failed" ? (
        <p className="ps-arrival-postcard__status" data-testid="arrival-status">
          到站自拍没有生成成功，留下这张手写明信片
        </p>
      ) : null}
    </div>
  );
}

/**
 * 演示收藏里的一张到站明信片（手写，没有自拍——演示里不拿任何图冒充 AI 自拍）：
 * 地点是演示世界的“演示小镇（示意）”（和卡包演示居民证同一个说法），话照后端模板的写法；时间是演示入住后半分钟（卡包演示入住在 40 天前）。
 * 只在演示模式出现（collection/module.tsx 的 fixture 服务）。
 */
export function demoArrivalPostcard(): CollectionItem {
  return {
    item_id: "fx-arrival-1",
    kind: "postcard",
    item_key: null,
    title: "来自演示小镇（示意）的到站明信片",
    obtained_at: atMin(-40 * 24 * 60 + 0.5),
    tradable: false,
    bound_to_pet: true,
    source_event_id: "arrival:fx-pet-001",
    data_origin: "fixture",
    note: "我到站啦！这里是演示小镇（示意），以后我就住在这儿了。给家里寄一张到站明信片，这是我在新家写下的第一句话～",
    image_url: null,
    image_status: null,
    place: "演示小镇（示意）",
    city: null,
  };
}
