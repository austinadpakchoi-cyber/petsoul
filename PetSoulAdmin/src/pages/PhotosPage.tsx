import { useState } from "react";
import { api } from "../api/client";
import type { PhotoAttemptView, SessionView } from "../api/types";
import { ErrorNote, ReasonDialog, useAsync, type ConfirmSpec } from "../components/ui";
import { ImagesDaily } from "./ImagesDaily";
import { PhotoRow } from "./PetPage";

/** 还没出图的照片：处理中 / 没画成 / 结果未确认三种明确分开；每张都说清用在玩家那边的哪里、卡在哪一步。 */
export default function PhotosPage({ session }: { session: SessionView }) {
  const { data, error, loading, reload } = useAsync(() => api.get<{ photos: PhotoAttemptView[] }>("/photos"), []);
  const [dialog, setDialog] = useState<ConfirmSpec | null>(null);
  const canRecover = session.staff.permissions.includes("task.recover");
  const canUsage = session.staff.permissions.includes("provider.read");

  if (loading) return <div className="empty">读取中…</div>;
  if (error) return <ErrorNote error={error} />;
  const photos = data?.photos ?? [];
  const unknowns = photos.filter((p) => p.call_state === "unknown");

  return (
    <>
      <div className="page-head">
        <h1>照片与任务</h1>
        <p>只列还没出图的。用户说「那张明信片一直没出来」，按「用在哪里」一栏的城市和时间对上是哪一张。</p>
      </div>

      {unknowns.length > 0 && (
        <div className="note warn">
          有 {unknowns.length} 张<strong>结果未确认</strong>：很可能已经发出去了，只是没等到回执。
          这既不是失败也不是没发送——后台不会自动重发，也不会抹掉费用记录。要处理请先向供应商核对。
        </div>
      )}

      {canUsage && <ImagesDaily />}

      <div className="card">
        <h2>处理中与没画成<small>{photos.length} 张</small></h2>
        {photos.length === 0 ? <div className="empty">没有积压的照片。</div> : (
          <table>
            <thead><tr><th>结果</th><th>宠物</th><th>用在哪里</th><th>进度</th><th>生图调用</th><th>最近更新</th><th>能做什么</th></tr></thead>
            <tbody>
              {photos.map((photo) => (
                <PhotoRow key={photo.illustration_id} photo={photo} showPet canRecover={canRecover} onRecover={() => setDialog({
                  title: "受控恢复这张照片",
                  placeholder: "例如：用户反馈照片一直没出来，供应商已恢复，重排一次",
                  confirmLabel: "恢复一次",
                  effects: ["只排一次新的尝试，已用的次数不清零。", "提交后只表示已受理：任务进了队列，还没开始画。"],
                  run: (reason, op) => api.post(`/photos/${photo.illustration_id}/recover`, { reason }, op),
                })} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {dialog && <ReasonDialog spec={dialog} onClose={() => setDialog(null)} onDone={reload} />}
    </>
  );
}
