import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { DietaryRestriction, FoodPreference, PreferenceSubject, TasteVector } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { Button, Card, Chip, ErrorState, Icon, ToggleChip } from "@/shared/ui";

const DIMENSIONS: Array<{ key: keyof TasteVector; label: string }> = [
  { key: "salty", label: "咸" },
  { key: "spicy", label: "辣" },
  { key: "oily", label: "油" },
  { key: "rich_broth", label: "浓汤" },
  { key: "sweet", label: "甜" },
];
const LEVELS: Array<{ value: number | null; label: string }> = [
  { value: -2, label: "很少" },
  { value: -1, label: "少一点" },
  { value: null, label: "随意" },
  { value: 1, label: "多一点" },
  { value: 2, label: "很爱" },
];

/**
 * 两套偏好分开编辑：宠物的旅途口味（它自己的性格）与主人的现实用餐偏好（含私密饮食限制）。
 * 饮食限制恒为私密，只用于给主人推荐。保存后版本 +1，已有推荐按新版本重新请求。
 */
export function PreferenceEditor({ petId, subject, variant }: { petId: string; subject: PreferenceSubject; variant?: string }) {
  const { food } = useServices();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const pref = useQuery({ queryKey: [...queryKeys.foodPreference(petId, subject), variant ?? "-"], queryFn: () => food.preference(petId, subject, variant) });
  const [draft, setDraft] = useState<FoodPreference | null>(null);
  const [restrictionText, setRestrictionText] = useState("");
  const keyRef = useRef(newIdempotencyKey("food-pref"));
  useEffect(() => {
    if (pref.data && !open) {
      setDraft(pref.data);
      setRestrictionText(pref.data.restrictions.map((r) => r.label).join("、"));
    }
  }, [pref.data, open]);
  const save = useMutation({
    mutationFn: (next: FoodPreference) => food.savePreference(subject, next, keyRef.current),
    onSuccess: (saved) => {
      keyRef.current = newIdempotencyKey("food-pref");
      queryClient.setQueryData([...queryKeys.foodPreference(petId, subject), variant ?? "-"], saved);
      void queryClient.invalidateQueries({ queryKey: ["food", "recommendations"] });
      setOpen(false);
    },
  });
  if (pref.isError) return <ErrorState error={pref.error} onRetry={() => void pref.refetch()} />;
  if (!pref.data || !draft) return null;
  const who = subject === "pet" ? "TA 的旅途口味" : "我的用餐偏好";
  const summary = DIMENSIONS.filter((d) => pref.data.taste[d.key] !== null)
    .map((d) => `${d.label}${(pref.data.taste[d.key] ?? 0) > 0 ? "+" : "−"}`)
    .join(" ");
  return (
    <Card flat className="ps-stack">
      <div className="ps-row" style={{ justifyContent: "space-between" }}>
        <div>
          <strong>{who}</strong>
          <div className="ps-muted">
            {pref.data.label} · 第 {pref.data.version} 版{summary ? ` · ${summary}` : ""}
          </div>
        </div>
        {env.dataMode === "live" ? (
          <Button size="sm" variant="ghost" icon={open ? "close" : "settings"} onClick={() => setOpen((v) => !v)}>
            {open ? "收起" : "调整"}
          </Button>
        ) : null}
      </div>
      {open ? (
        <form
          className="ps-stack"
          onSubmit={(e) => {
            e.preventDefault();
            const restrictions: DietaryRestriction[] =
              subject === "owner"
                ? restrictionText
                    .split(/[、,，\s]+/)
                    .map((t) => t.trim())
                    .filter(Boolean)
                    .slice(0, 8)
                    .map((label) => ({ kind: "avoid", label, private: true }))
                : [];
            save.mutate({ ...draft, label: draft.label.trim() || "我的口味", restrictions });
          }}
        >
          <div className="ps-field">
            <label htmlFor={`pref-label-${subject}`}>偏好名字</label>
            <input id={`pref-label-${subject}`} className="ps-input" maxLength={20} value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.target.value })} />
          </div>
          {DIMENSIONS.map((d) => (
            <div key={d.key} className="ps-field">
              <span className="ps-muted">{d.label}</span>
              <div className="ps-segmented" role="group" aria-label={`${d.label}的偏好`}>
                {LEVELS.map((l) => (
                  <ToggleChip key={l.label} pressed={draft.taste[d.key] === l.value} onToggle={() => setDraft({ ...draft, taste: { ...draft.taste, [d.key]: l.value } })}>
                    {l.label}
                  </ToggleChip>
                ))}
              </div>
            </div>
          ))}
          {subject === "owner" ? (
            <div className="ps-field">
              <label htmlFor="pref-restrictions">不吃/过敏（用顿号分隔）</label>
              <input id="pref-restrictions" className="ps-input" value={restrictionText} onChange={(e) => setRestrictionText(e.target.value)} placeholder="比如：花生、牛肉" />
              <span className="ps-muted">
                <Icon name="lock" size={12} /> 只用于给你推荐，不会出现在朋友圈或任何公开页面。
              </span>
            </div>
          ) : (
            <Chip>这是 TA 自己的口味，不会改动你的现实用餐偏好</Chip>
          )}
          <Button type="submit" variant="primary" loading={save.isPending}>
            保存（第 {pref.data.version + 1} 版）
          </Button>
          {save.isError ? <ErrorState error={save.error} /> : null}
        </form>
      ) : null}
    </Card>
  );
}
