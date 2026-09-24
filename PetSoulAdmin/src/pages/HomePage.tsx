/**
 * 家里的东西：仓库（库存与变动）、居民订单、菜地、偷菜记录。只读。
 * 仓库属于这个家（家里的宠物共用）；星币不在这里，在每只宠物自己的游戏账本里。
 * 仓库与居民订单是游戏资产，要「看星币流水与家里的库存」权限；菜地与偷菜记录有「查用户与家庭」就能看。
 * 玩家编号都换成名字（后端随数据给 `people`），点名字进用户页。
 */
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import type { HomeView, SessionView } from "../api/types";
import { Player } from "../components/player";
import { ErrorNote, Pill, useAsync, when } from "../components/ui";
import { Code, PermissionName, Term } from "../labels";

export default function HomePage({ session }: { session: SessionView }) {
  const { homeId = "" } = useParams();
  const { data, error, loading } = useAsync(() => api.get<HomeView>(`/homes/${homeId}`), [homeId]);
  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;
  const canPets = session.staff.permissions.includes("pet.read");

  return (
    <>
      <div className="page-head">
        <h1>家里的东西</h1>
        <Code value={homeId} />
        <p>{data.activated_at ? `${when(data.activated_at)} 入住` : "还没完成入住"} · 住着：
          {data.pets.length === 0 ? "没有宠物" : data.pets.map((pet, i) => (
            <span key={pet.pet_id}>{i > 0 && "、"}{canPets ? <Link to={`/pets/${pet.pet_id}`}>{pet.name}</Link> : pet.name}</span>))}</p>
      </div>
      <div className="note plain">{data.note}</div>

      <div className="grid cols-2">
        <div className="card">
          <h2>仓库</h2>
          {data.pantry === null ? (
            <div className="card-body"><div className="note plain">{data.pantry_note ?? "这个库里还没有仓库记录，查不了。"}</div></div>
          ) : data.pantry.stock.length === 0 ? <div className="empty">仓库是空的。</div> : (
            <table>
              <thead><tr><th>东西</th><th className="num">数量</th><th>最近变动</th></tr></thead>
              <tbody>
                {data.pantry.stock.map((row) => (
                  <tr key={row.item_key}>
                    <td><Term code={row.item_key} label={row.item_label} /></td>
                    <td className="num">{row.qty}</td>
                    <td>{when(row.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card">
          <h2>菜地{data.farm?.patrol?.active && <small>主人正在巡院，到 {when(data.farm.patrol.until)}</small>}</h2>
          {data.farm === null ? <div className="empty">这个库里还没有菜地记录，查不了。</div> : (
            <table>
              <thead><tr><th>第几块</th><th>种的</th><th>状态</th><th>什么时候熟</th><th className="num">被偷</th></tr></thead>
              <tbody>
                {data.farm.plots.map((plot) => (
                  <tr key={plot.slot}>
                    <td>第 {plot.slot + 1} 块</td>
                    <td>{plot.crop_key ? <Term code={plot.crop_key} label={plot.crop_label} /> : "—"}</td>
                    <td><Term family="plot_state" code={plot.state} /></td>
                    <td>{plot.crop_key ? when(plot.ripe_at) : "—"}</td>
                    <td className="num">{plot.stolen_units > 0 ? <Pill tone="warn">{plot.stolen_units} 份</Pill> : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {data.pantry !== null && data.pantry.moves.length > 0 && (
        <div className="card">
          <h2>仓库变动<small>最近 {data.pantry.moves.length} 条</small></h2>
          <table>
            <thead><tr><th>时间</th><th>东西</th><th className="num">变化</th><th>怎么来的 / 去哪了</th><th>谁的操作</th></tr></thead>
            <tbody>
              {data.pantry.moves.map((move, i) => (
                <tr key={i}>
                  <td>{when(move.created_at)}</td>
                  <td><Term code={move.item_key} label={move.item_label} /></td>
                  <td className="num">{move.delta > 0 ? `+${move.delta}` : move.delta}</td>
                  <td>{move.reason ?? "—"}</td>
                  <td>{move.actor_user_id ? <Player id={move.actor_user_id} name={data.people?.[move.actor_user_id]} /> : "系统"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Orders data={data} />

      <div className="card">
        <h2>偷菜记录</h2>
        {data.steals === null ? <div className="empty">这个库里还没有偷菜记录，查不了。</div> : (
          <div className="grid cols-2" style={{ padding: 12 }}>
            <div>
              <h3 style={{ margin: "0 0 6px", fontSize: 14 }}>别人来这个家偷的（{data.steals.from_this_home.length}）</h3>
              {data.steals.from_this_home.length === 0 ? <div className="hint">没有。</div> : data.steals.from_this_home.map((s, i) => (
                <div key={i}>{when(s.created_at)} · 偷走 {s.units} 份 · 来偷的是 <Player id={s.thief_user_id} name={data.people?.[s.thief_user_id]} /></div>
              ))}
            </div>
            <div>
              <h3 style={{ margin: "0 0 6px", fontSize: 14 }}>这家人去别人家偷的（{data.steals.by_this_household.length}）</h3>
              {data.steals.by_this_household.length === 0 ? <div className="hint">没有。</div> : data.steals.by_this_household.map((s, i) => (
                <div key={i}>{when(s.created_at)} · 偷了 {s.units} 份 · <Link to={`/homes/${s.victim_home_id}`}>被偷的那个家</Link><Code value={s.victim_home_id} /></div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

/** 杂货铺居民每天来下的订单：交了多少菜、付多少星币（进宠物自己的游戏账本）。没有库存权限时后端不给（null）。 */
function Orders({ data }: { data: HomeView }) {
  const orders = data.orders;
  if (orders === undefined) return null;
  return (
    <div className="card">
      <h2>居民订单<small>交菜换星币；星币记在交单那只宠物的游戏账本里</small></h2>
      {orders === null ? (
        <div className="card-body"><div className="note plain">{data.pantry === null && data.pantry_note
          ? <>居民订单也是游戏资产，要「<PermissionName code="economy.read" />」权限才能看。</>
          : "这个库里还没有订单记录，查不了。"}</div></div>
      ) : orders.length === 0 ? <div className="empty">还没有订单。</div> : (
        <table>
          <thead><tr><th>哪天</th><th>谁要的</th><th>要什么</th><th className="num">数量</th><th className="num">付多少星币</th><th>交了没</th></tr></thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.order_id}>
                <td>{order.day} · 第 {order.slot + 1} 单<Code value={order.order_id} /></td>
                <td>{order.resident ?? "—"}</td>
                <td><Term code={order.item_key} label={order.item_label} /></td>
                <td className="num">{order.qty}</td>
                <td className="num">{order.reward}</td>
                <td>{order.fulfilled_at ? <Pill tone="ok">{when(order.fulfilled_at)} 交了</Pill> : <Pill tone="muted">还没交</Pill>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
