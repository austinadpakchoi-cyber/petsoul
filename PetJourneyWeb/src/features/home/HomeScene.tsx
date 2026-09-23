import { createContext, useContext, useState } from "react";
import { Link, useSearchParams } from "react-router";
import type { HomeSnapshot, PlotSummary } from "@/shared/contracts";
import { Button, Icon, PetAvatar, Sheet } from "@/shared/ui";
import courtyard from "./assets/living/courtyard-base.webp";
import room from "./assets/living/room-base.webp";
import soil from "./assets/living/plot-soil.webp";
import cup from "./assets/living/ordinary-cup.webp";
import { cropVisual } from "@/features/farm/cropVisual";

/** Only the isolated internal test harness supplies a character. No default pet identity. */
export const LivingCharacterContext = createContext<{
  petId: string;
  rest: string;
  sit: string;
  bag: string;
} | null>(null);

export function PlotArt({ plot }: { plot: PlotSummary }) {
  const growing = plot.stage === "growing";
  const ripe = plot.stage === "ripe";
  const cropClass = ripe ? `is-${plot.crop_key ?? "unknown"}` : "is-leaves";
  return (
    <span className={`ps-living-plot-art is-${plot.stage}`} aria-hidden="true">
      <img className="ps-living-soil" src={soil} alt="" />
      {growing || ripe ? (
        <img
          className={`ps-living-crop ${cropClass}`}
          src={cropVisual(plot.crop_key, ripe ? "ripe" : "growing")}
          alt=""
        />
      ) : null}
    </span>
  );
}

export function HomeScene({ snapshot }: { snapshot: HomeSnapshot }) {
  const [params, setParams] = useSearchParams();
  const inside = params.get("room") === "inside";
  const home = snapshot.presence === "at_home";
  const character = useContext(LivingCharacterContext);
  const sprite =
    snapshot.data_origin === "fixture" &&
    character?.petId === snapshot.pet.pet_id
      ? character
      : null;
  const [sitting, setSitting] = useState(false);
  const [petOpen, setPetOpen] = useState(false);
  const [noteOpen, setNoteOpen] = useState<"object" | "away" | null>(null);
  const object = snapshot.welcome?.details.find(
    (detail) => detail.kind === "favorite_object",
  );
  const changeRoom = (value: boolean) => {
    const next = new URLSearchParams(params);
    if (value) next.set("room", "inside");
    else next.delete("room");
    setParams(next);
  };
  const selectPlot = (id: string) => {
    const next = new URLSearchParams(params);
    next.set("plot", id);
    setParams(next);
  };
  const plotLabel = (plot: PlotSummary) =>
    plot.stage === "harvested" ? "空出来啦" : (plot.crop_label ?? "种点什么");
  const plotAction = (plot: PlotSummary) =>
    plot.stage === "ripe"
      ? "可收获"
      : plot.stage === "growing"
        ? "正在长"
        : "可以种植";
  return (
    <section
      className={`ps-living-scene ${inside ? "is-inside" : "is-courtyard"}`}
      data-presence={snapshot.presence}
      aria-label={inside ? "共同的家·屋内" : "共同的家·庭院"}
    >
      <img
        className="ps-living-background"
        src={inside ? room : courtyard}
        alt=""
        fetchPriority="high"
      />
      <header className="ps-living-header">
        <div className="ps-living-identity">
          {sprite ? (
            <img
              className="ps-living-avatar"
              src={sprite.sit}
              alt={snapshot.pet.name}
            />
          ) : (
            <PetAvatar
              petId={snapshot.pet.pet_id}
              name={snapshot.pet.name}
              species={snapshot.pet.species}
              photoUrl={snapshot.pet.photo_url}
              size={38}
            />
          )}
          <div>
            <span>我们的家</span>
            <h1>{snapshot.pet.name}的小窝</h1>
          </div>
        </div>
        <Link
          to="/market"
          className="ps-living-wallet"
          aria-label={`旅费 ${snapshot.wallet.balance}，查看仓库与集市`}
        >
          <Icon name="coin" size={17} />
          <strong data-testid="home-wallet">{snapshot.wallet.balance}</strong>
        </Link>
        <nav className="ps-living-switch" aria-label="家里的空间">
          <button
            type="button"
            aria-pressed={!inside}
            onClick={() => changeRoom(false)}
          >
            庭院
          </button>
          <button
            type="button"
            aria-pressed={inside}
            onClick={() => changeRoom(true)}
          >
            屋内
          </button>
        </nav>
        <Link
          to="/settings"
          className="ps-living-settings"
          aria-label="账号与设置"
        >
          <Icon name="settings" size={19} />
        </Link>
      </header>
      {!inside ? (
        <button
          type="button"
          className="ps-living-door ps-living-label"
          onClick={() => changeRoom(true)}
        >
          <Icon name="home" size={14} /> 进屋
        </button>
      ) : (
        <Link to="/collection" className="ps-living-cabinet ps-living-label">
          <Icon name="gift" size={14} /> 看看收藏
        </Link>
      )}
      {home ? (
        <>
          <button
            type="button"
            className={`ps-living-pet ${sitting ? "is-sitting" : ""} ${sprite ? "is-photo" : "is-portrait"}`}
            data-testid="home-pet"
            onClick={() => setPetOpen(true)}
            aria-label={`看看 ${snapshot.pet.name}`}
          >
            {sprite ? (
              <>
                <span className="ps-living-pet__shadow" aria-hidden="true" />
                <img
                  src={sitting ? sprite.sit : sprite.rest}
                  alt={`${snapshot.pet.name}的内部测试形象`}
                />
              </>
          ) : (
              <span className={`ps-living-pet__identity${snapshot.pet.photo_url ? " has-photo" : ""}`}>
                {snapshot.pet.photo_url ? <img src={snapshot.pet.photo_url} alt="" /> : <strong>{snapshot.pet.name.trim().slice(0, 1) || "·"}</strong>}
                <small>{snapshot.pet.photo_generated ? "AI 生成形象" : snapshot.pet.photo_url ? snapshot.pet.name : "暂无照片"}</small>
              </span>
            )}
          </button>
          {sprite && !inside ? (
            <img
              className="ps-living-bag"
              src={sprite.bag}
              alt=""
              data-testid="home-bag"
            />
          ) : null}
        </>
      ) : null}
      {!inside ? (
        <img
          className="ps-living-cup"
          src={cup}
          alt=""
          data-testid="home-cup"
        />
      ) : null}
      {object ? (
        <button
          type="button"
          className="ps-living-memento ps-living-label"
          onClick={() => setNoteOpen("object")}
        >
          <Icon name="bookmark" size={14} /> {object.text}
        </button>
      ) : null}
      {!home && snapshot.journey ? (
        <button
          type="button"
          className="ps-living-note"
          onClick={() => setNoteOpen("away")}
          aria-label="打开留在家里的便笺"
        >
          我出门啦<span>点开便笺</span>
        </button>
      ) : null}
      {!inside ? (
        <>
          <Link
            to="/communicator"
            className={`ps-living-mail ps-living-label ${snapshot.unread.messages > 0 ? "has-mail" : ""}`}
            aria-label={`打开信箱，${snapshot.unread.messages} 条未读消息`}
          >
            {snapshot.unread.messages > 0 ? (
              <span className="ps-living-envelope">
                <Icon name="mail" size={24} />
              </span>
            ) : null}
            <span>
              信箱
              {snapshot.unread.messages > 0
                ? ` · ${snapshot.unread.messages}`
                : ""}
            </span>
          </Link>
          <div className="ps-living-garden" aria-label="庭院菜地">
            {snapshot.plots.map((plot, index) => (
              <button
                key={plot.plot_id}
                type="button"
                className={`ps-living-plot is-${plot.stage}`}
                data-stage={plot.stage}
                aria-label={`第 ${index + 1} 块菜地，${plotLabel(plot)}，${plotAction(plot)}`}
                onClick={() => selectPlot(plot.plot_id)}
              >
                <PlotArt plot={plot} />
                <span className="ps-living-plot-name">{plotLabel(plot)}</span>
                <strong
                  className={`ps-living-plot-state ${plot.stage === "ripe" ? "is-ready" : ""}`}
                >
                  {plotAction(plot)}
                </strong>
              </button>
            ))}
          </div>
          <Link
            to="/market"
            className="ps-living-pantry ps-living-label"
            aria-label={`打开仓库与集市，仓库有 ${snapshot.pantry.length} 种物品`}
          >
            <Icon name="gift" size={14} /> 仓库
          </Link>
        </>
      ) : null}
      {petOpen && home ? (
        <Sheet
          title={`陪 ${snapshot.pet.name} 待一会儿`}
          subtitle={sprite ? "内部角色动作示例，不改变宠物真实状态" : "TA 在家"}
          onClose={() => setPetOpen(false)}
        >
          <div className="ps-stack">
            {sprite ? (
              <Button
                variant="leaf"
                onClick={() => {
                  setSitting(!sitting);
                  setPetOpen(false);
                }}
              >
                {sitting ? "让 TA 趴着休息" : "陪 TA 坐一会儿"}
              </Button>
            ) : null}
            <Link className="ps-btn ps-btn--secondary" to="/communicator">
              给 TA 捎句话
            </Link>
            <Link className="ps-btn ps-btn--ghost" to="/journey">
              看看下一段旅途
            </Link>
          </div>
        </Sheet>
      ) : null}
      {noteOpen ? (
        <Sheet
          title={
            noteOpen === "object" ? "你为 TA 留下的叮嘱" : "留在家里的小便笺"
          }
          onClose={() => setNoteOpen(null)}
        >
          <p>
            {noteOpen === "object" ? object?.text : snapshot.journey?.headline}
          </p>
          <Link
            className="ps-btn ps-btn--leaf"
            to={
              noteOpen === "object"
                ? "/onboarding/reception?mode=supplement"
                : "/journey"
            }
          >
            {noteOpen === "object" ? "查看与补充叮嘱" : "去陪 TA"}
          </Link>
        </Sheet>
      ) : null}
    </section>
  );
}
