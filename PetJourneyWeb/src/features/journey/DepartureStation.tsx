import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import type { DestinationOption, HomeSnapshot, JourneyMapSnapshot, JourneySuggestion } from "@/shared/contracts";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import { Button, Chip, ErrorState, Icon, QueryView, type IconName } from "@/shared/ui";
import courtyard from "@/features/home/assets/living/courtyard-base.webp";
import { PawMark, petPortraitUrl } from "@/features/pets/PetPortrait";

const MODE_ICON: Record<string, IconName> = { walk: "compass", taxi: "car", car: "car", ferry: "ship", flight: "plane", train: "train" };
const MODE_TEXT: Record<string, string> = { walk: "步行", taxi: "打车", car: "自驾", ferry: "轮渡", flight: "飞机", train: "火车" };

function minutesText(total: number): string {
  if (total < 60) return `约 ${total} 分钟`;
  const h = Math.floor(total / 60);
  const m = total % 60;
  return m ? `约 ${h} 小时 ${m} 分` : `约 ${h} 小时`;
}

const SUGGESTION_TEXT: Record<string, string> = {
  pending: "你的建议已经放进 TA 心里了；去不去、什么时候去，由 TA 决定。",
  accepted: "TA 听了你的建议，去过这里了。",
  passed: "这阵子 TA 没选它，下次可以再聊聊。",
  replaced: "你后来换了一个建议。",
};

/** 一个地方的“悄悄话”：只有建议，没有替 TA 出发的按钮（出门由 TA 自主决定）。 */
function SuggestPlace({ option, petId, suggestion, onSuggested }: {
  option: DestinationOption;
  petId: string;
  suggestion: JourneySuggestion | null;
  onSuggested: () => void;
}) {
  const { transport } = useServices();
  const available = option.available !== false;
  const suggest = useMutation({ mutationFn: () => transport.suggest(option.destination_key, petId), onSuccess: onSuggested });
  const pending = suggestion?.status === "pending";
  return (
    <article className={`ps-suggest-place${pending ? " is-pending" : ""}`}>
      <div className="ps-suggest-place__head">
        <strong>{option.title}</strong>
        <span>{option.city} · {option.modes.map((m) => MODE_TEXT[m] ?? m).join(" / ")} · 往返{minutesText(option.total_minutes)}</span>
      </div>
      <p>{option.summary}</p>
      <div className="ps-suggest-place__meta">
        {option.modes.slice(0, 1).map((m) => <Icon key={m} name={MODE_ICON[m] ?? "journey"} size={15} />)}
        <span>路费约 {option.fee} 星币</span>
        {option.wish_match ? <Chip tone="leaf" icon="bookmark">{option.wish_match}</Chip> : null}
      </div>
      {!available ? <p role="status" className="ps-suggest-place__note is-muted">这里暂时去不了：{option.unavailable_reason || "交通资料暂不可用"}</p> : null}
      {suggestion ? <p role="status" className="ps-suggest-place__note">{SUGGESTION_TEXT[suggestion.status] ?? SUGGESTION_TEXT.pending}</p> : null}
      <Button variant={pending ? "secondary" : "leaf"} size="sm" disabled={!available || pending} loading={suggest.isPending} onClick={() => suggest.mutate()}>
        {pending ? "TA 在考虑" : "悄悄告诉 TA"}
      </Button>
      {suggest.isError ? <ErrorState error={suggest.error} /> : null}
    </article>
  );
}

/**
 * 在家时的旅途页。出不出门、去哪里、什么时候走由 TA 自己决定（后端生活节奏），主人只能“悄悄告诉 TA 一个地方”。
 * 不提供替 TA 立即出发的按钮：那是主人代替宠物决定，和“宠物自主”相反。
 */
export function JourneyAtHome({ home, last }: { home: HomeSnapshot; last: JourneyMapSnapshot | null }) {
  const { transport } = useServices();
  const userId = useOptionalCurrentHousehold()?.userId;
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const pet = home.pet;
  const otherGardenKeepers = (home.guard.guarding_pets ?? []).filter((id) => id !== pet.pet_id);
  const destinations = useQuery({ queryKey: queryKeys.destinationsFor(userId ?? "-", pet.pet_id), queryFn: ({ signal }) => transport.destinations(pet.pet_id, signal), enabled: open });
  const suggestions = useQuery({ queryKey: queryKeys.journeySuggestions(userId ?? "-", pet.pet_id), queryFn: ({ signal }) => transport.suggestions(pet.pet_id, signal), retry: false });
  const pending = suggestions.data?.find((item) => item.status === "pending") ?? null;
  return (
    <div className="ps-trip-home">
      <section className="ps-trip-home__stage" aria-label={`${pet.name} 在家`}>
        <img className="ps-trip-home__scene" src={courtyard} alt="" />
        <span className={`ps-trip-home__pet${petPortraitUrl(pet.photo_url) ? " has-photo" : ""}`} aria-hidden="true">
          {petPortraitUrl(pet.photo_url) ? <img src={petPortraitUrl(pet.photo_url)!} alt="" /> : <PawMark size={26} />}
        </span>
        <div className="ps-trip-home__copy">
          <span className="ps-trip-home__eyebrow"><i aria-hidden="true" />此刻 · 在家</span>
          <h2>{pet.name} 在家</h2>
          <p>出不出门、去哪里、什么时候走，都由 TA 自己决定。{home.wallet.balance < 10 ? "星币不多的时候，TA 多半就在附近走走。" : ""}</p>
          <p className="ps-trip-home__garden">{otherGardenKeepers.length > 0 ? `TA 出门时，还有 ${otherGardenKeepers.length} 位伙伴在家照看菜园。` : "TA 出门后，院子交给你照看；没人巡院时，邻居可能来摘一点。"}</p>
        </div>
      </section>
      {pending ? (
        <p className="ps-trip-home__pending" role="status"><Icon name="heart" size={15} /> 你悄悄说过的「{pending.title}」，TA 还在想。</p>
      ) : null}
      {last && last.lifecycle === "completed" ? (
        <Link className="ps-trip-home__last" to="/collection">
          <Icon name="check" size={17} />
          <span>上一次去了 {last.destination_title ?? "外面"}，已经平安回家。<small>带回的东西在回忆与收藏里</small></span>
          <Icon name="chevron" size={15} />
        </Link>
      ) : null}
      <Link className="ps-departure-archive" to="/guides"><Icon name="bookmark" size={17} /> 翻看 TA 的旅行手账 <Icon name="chevron" size={15} /></Link>
      <section className="ps-trip-suggest">
        <button type="button" className="ps-trip-suggest__toggle" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          <span><strong>悄悄告诉 TA 一个地方</strong><small>TA 会放在心上，接下来一天出门时会想起它；去不去由 TA 决定。</small></span>
          <Icon name="chevron" size={17} />
        </button>
        {open ? (
          <div className="ps-trip-suggest__list">
            {suggestions.isError ? <ErrorState error={suggestions.error} onRetry={() => void suggestions.refetch()} /> : null}
            <QueryView query={destinations} isEmpty={(list) => list.length === 0}>
              {(list) => (
                <>
                  {list.map((option) => (
                    <SuggestPlace
                      key={option.destination_key}
                      option={option}
                      petId={pet.pet_id}
                      suggestion={suggestions.data?.find((item) => item.destination_key === option.destination_key) ?? null}
                      onSuggested={() => {
                        void queryClient.invalidateQueries({ queryKey: queryKeys.journeySuggestions(userId ?? "-", pet.pet_id) });
                        void queryClient.invalidateQueries({ queryKey: ["communicator"] });
                      }}
                    />
                  ))}
                </>
              )}
            </QueryView>
          </div>
        ) : null}
      </section>
    </div>
  );
}
