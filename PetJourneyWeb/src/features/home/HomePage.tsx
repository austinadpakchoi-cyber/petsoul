import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import type { HomeSnapshot } from "@/shared/contracts";
import { currentLeg, remainingMs } from "@/shared/journey/vehicle";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useActiveHome, useCurrentHousehold } from "@/shared/session/householdContext";
import { Slot } from "@/shared/slots/Slot";
import { formatDuration, useNow } from "@/shared/time/clock";
import { Icon, Page, QueryView } from "@/shared/ui";
import { HomeScene } from "./HomeScene";
import "./home.css";

function Participation({ snapshot }: { snapshot: HomeSnapshot }) {
  const [params, setParams] = useSearchParams();
  const { transport } = useServices();
  const now = useNow(1000);
  const away = snapshot.presence !== "at_home" && Boolean(snapshot.journey);
  const map = useQuery({
    queryKey: queryKeys.journeyMap(snapshot.pet.pet_id),
    queryFn: () => transport.journeyMap(snapshot.pet.pet_id),
    enabled: away,
    refetchInterval: 30_000,
  });
  const leg = map.data ? currentLeg(map.data) : null;
  const ripe = snapshot.plots.filter((p) => p.stage === "ripe");
  const hasMail = snapshot.unread.messages > 0;
  const title = away
    ? snapshot.journey!.headline
    : ripe.length
      ? `${ripe.length} 块菜地成熟了`
      : hasMail
        ? "信箱里有新消息"
        : snapshot.presence === "at_home"
          ? `${snapshot.pet.name} 在家`
          : "小窝已经准备好";
  const detail = away
    ? leg
      ? `预计还有 ${formatDuration(remainingMs(leg.times, now))} · 院子依然可以照料`
      : "家里的阳光还在，随时可以去看看 TA。"
    : ripe.length
      ? "收成先进仓库，卖出后才增加旅费。"
      : hasMail
        ? `${snapshot.unread.messages} 条未读，打开看看。`
        : "在自己的节奏里，过一个平常的日子。";
  return (
    <section className="ps-home-participation" aria-label="此刻可以做的事">
      <span className="ps-home-participation__eyebrow">此刻 · 一起生活</span>
      <h2>{title}</h2>
      <p>{detail}</p>
      {!away && ripe.length ? (
        <button
          type="button"
          className="ps-btn ps-btn--leaf"
          onClick={() => {
            const next = new URLSearchParams(params);
            next.set("plot", ripe[0].plot_id);
            next.delete("room");
            setParams(next);
          }}
        >
          去收菜 <Icon name="chevron" size={16} />
        </button>
      ) : (
        <Link
          className="ps-btn ps-btn--leaf"
          to={away ? "/journey" : hasMail ? "/communicator" : "/journey"}
        >
          {away ? "去陪 TA" : hasMail ? "打开看看" : "准备下一次出发"}{" "}
          <Icon name="chevron" size={16} />
        </Link>
      )}
    </section>
  );
}

export function HomeBody({ snapshot, canAddCompanion = false }: { snapshot: HomeSnapshot; canAddCompanion?: boolean }) {
  return (
    <div className="ps-home-body">
      <HomeScene snapshot={snapshot} />
      {snapshot.catching_up ? <p className="ps-home-catching-up" role="status">世界正在补记刚发生的小事；位置照常更新，来信、工资与收藏可能稍后出现。</p> : null}
      <Participation snapshot={snapshot} />
      <div className="ps-home-below">
        <Slot name="home.welcome" props={{ snapshot }} />
        <Slot name="home.panels" props={{ snapshot }} />
        <nav className="ps-home-quiet-links" aria-label="生活与回忆">
          <Link to="/photos?scene=home">给 TA 拍一张</Link>
          <Link to="/households/manage">我们的家</Link>
          <Link to="/life">工作与证件</Link>
          <Link to="/collection">我的收藏</Link>
          <Link to="/onboarding/reception?mode=supplement">入住叮嘱</Link>
          {canAddCompanion ? <Link to="/pets/new">给这个家添伙伴</Link> : null}
        </nav>
      </div>
    </div>
  );
}

export function HomePage() {
  const query = useActiveHome({ refetchInterval: 60_000 });
  const { household } = useCurrentHousehold();
  return (
    <Page className="ps-home-page">
      <QueryView query={query}>
        {(snapshot) => <HomeBody snapshot={snapshot} canAddCompanion={household?.role === "admin"} />}
      </QueryView>
    </Page>
  );
}
