import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { SearchView } from "../api/types";
import { ErrorNote, Pill, useAsync, when } from "../components/ui";
import { Code, Term } from "../labels";

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const term = params.get("q") ?? "";
  const [draft, setDraft] = useState(term);
  useEffect(() => { setDraft(term); }, [term]);  // 从顶部全局检索跳过来时，本页输入框跟着 URL 走
  const { data, error, loading } = useAsync(
    () => (term ? api.get<SearchView>(`/search?q=${encodeURIComponent(term)}`) : Promise.resolve(null)),
    [term],
  );

  return (
    <>
      <div className="page-head">
        <h1>用户与宠物</h1>
        <p>按用户编号、用户名、宠物编号或宠物名检索。查询不会推进游戏，也不会发起模型调用。</p>
      </div>

      <div className="card">
        <div className="card-body">
          <form className="row" onSubmit={(e) => { e.preventDefault(); setParams(draft.trim() ? { q: draft.trim() } : {}); }}>
            <div style={{ flex: 3 }}>
              <label htmlFor="q">检索</label>
              <input id="q" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="PU-xxxxxxxx / 用户名 / PJ-xxxxxxxx / 宠物名" />
            </div>
            <div style={{ flex: 0, minWidth: 90 }}><button className="primary" type="submit">查找</button></div>
          </form>
        </div>
      </div>

      <ErrorNote error={error} />
      {!term && <div className="empty">输入条件开始检索。</div>}
      {term && loading && <div className="empty">检索中…</div>}
      {data && (
        <>
          <div className="card">
            <h2>账号<small>{data.users.length} 条</small></h2>
            {data.users.length === 0 ? <div className="empty">没有命中。{data.note}</div> : (
              <table>
                <thead><tr><th>用户</th><th>账号状态</th><th className="num">家庭</th><th className="num">宠物</th><th>注册时间</th><th>按什么找到的</th></tr></thead>
                <tbody>
                  {data.users.map((user) => (
                    <tr key={user.user_id}>
                      <td>
                        <Link to={`/users/${user.user_id}`}>{user.username ?? user.display_name ?? user.user_id}</Link>
                        <Code value={user.user_id} />
                      </td>
                      <td>{user.account_status === "frozen" ? <Pill tone="danger">已冻结</Pill> : <Pill tone="ok">正常</Pill>}</td>
                      <td className="num">{user.household_count}</td>
                      <td className="num">{user.pet_count}</td>
                      <td>{when(user.created_at)}</td>
                      <td><Pill tone="muted"><Term family="search_match" code={user.matched_on} /></Pill></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="card">
            <h2>宠物<small>{data.pets.length} 条</small></h2>
            {data.pets.length === 0 ? <div className="empty">没有命中。</div> : (
              <table>
                <thead><tr><th>宠物</th><th>物种</th><th>家庭</th><th>诊断</th></tr></thead>
                <tbody>
                  {data.pets.map((pet) => (
                    <tr key={pet.pet_id}>
                      <td>{pet.name}<Code value={pet.pet_id} /></td>
                      <td><Term family="species" code={pet.species} /></td>
                      <td>{pet.household_id ? <>在家庭里<Code value={pet.household_id} /></> : "还没有家（待领养的居民）"}</td>
                      <td><Link to={`/pets/${pet.pet_id}`}>打开宠物</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </>
  );
}
