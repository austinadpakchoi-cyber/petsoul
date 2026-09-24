/**
 * 每天生成了多少张图（最近 30 天）：按记账日、按用途，分「出图了 / 发出去没画成 / 没发出 / 结果未确认 / 还在路上」。
 * 「调用」是发起了几次，「计入」是计进额度的张数（没发出的计 0、在途的还没计）——两个数分开，不混成一个。
 * 数据只来自额度账；上限是运行配置的现值，这里只显示、不改。要「看调用用量与平台成本」权限。
 */
import { api } from "../api/client";
import type { ImageDayCell, ImagesDailyView } from "../api/types";
import { ErrorNote, Pill, useAsync } from "../components/ui";
import { Term } from "../labels";

const BUCKETS = ["ok", "failed", "not_sent", "unknown", "inflight"] as const;
const TONE: Record<string, "ok" | "danger" | "muted" | "unknown" | "warn"> = {
  ok: "ok", failed: "danger", not_sent: "muted", unknown: "unknown", inflight: "warn",
};

export function ImagesDaily() {
  const { data, error, loading } = useAsync(() => api.get<ImagesDailyView>("/usage/images-daily"), []);
  return (
    <div className="card">
      <h2>每天生成了多少张图<small>最近 30 天 · 按 UTC 记账日（北京时间 08:00 换日）</small></h2>
      {loading ? <div className="empty">读取中…</div> : error ? <div className="card-body"><ErrorNote error={error} /></div>
        : !data ? null : data.days === null ? <div className="empty">{data.note}</div> : (
          <>
            <table>
              <thead>
                <tr>
                  <th>哪天</th>
                  {(data.purposes ?? []).map((p) => <th key={p}><Term family="purpose" code={p} /></th>)}
                  <th className="num">合计：调用 / 计入</th>
                  <th>全站额度</th>
                </tr>
              </thead>
              <tbody>
                {data.days.map((day) => (
                  <tr key={day.day}>
                    <td>{day.day}{day.day === data.today && <> <Pill tone="muted">今天</Pill></>}</td>
                    {(data.purposes ?? []).map((p) => <td key={p}><Cell cell={day.purposes[p]} /></td>)}
                    <td className="num">{day.total.calls} / {day.total.units}</td>
                    <td>{day.global_counter
                      ? <>已用 {day.global_counter.used}{day.global_counter.inflight ? `＋在途 ${day.global_counter.inflight}` : ""} / 上限 {data.caps?.global_daily}
                        {day.global_counter.used + day.global_counter.inflight >= (data.caps?.global_daily ?? Infinity) && <> <Pill tone="warn">到上限了</Pill></>}</>
                      : <span className="hint">这天没有计数</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="card-body">
              <p className="section-note" style={{ marginTop: 0 }}>
                上限（运行配置的现值）：全站每天 {data.caps?.global_daily} 张；每只宠物每个用途每天 {data.caps?.per_pet_daily} 张。{data.note}
              </p>
            </div>
          </>
        )}
    </div>
  );
}

function Cell({ cell }: { cell: ImageDayCell | undefined }) {
  if (!cell || cell.calls === 0) return <span className="hint">没有</span>;
  return (
    <>
      <div>调用 {cell.calls} · 计入 {cell.units}</div>
      <div style={{ marginTop: 2 }}>
        {BUCKETS.filter((b) => cell.buckets[b]).map((b) => (
          <span key={b} style={{ marginRight: 4 }}><Pill tone={TONE[b]}><Term family="image_bucket" code={b} /> {cell.buckets[b]}</Pill></span>
        ))}
      </div>
    </>
  );
}
