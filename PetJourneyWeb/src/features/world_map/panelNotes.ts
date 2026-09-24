/**
 * 主状态面板的提醒：来源、先后与筛选（方案 v2.1 第 3.2 节：提醒全部合进面板，收起时只显示最重要的一条，其余点开再看）。
 * 先后：TA 的来信（信箱）> 一起听 / 一起看（车上活动，有时效）> 这趟旅途（到了让 TA 挑一家）> 驾校 > 旅行心愿（想去哪里 / 还差什么，TRV-06，
 * 来源 journey/travelPlan/wishNote）> 系统提示（世界正在更新）；同一种里保持来的先后。收起 / 展开在 ./StatusPanel。
 * 一起听、这趟旅途两种来自行程快照（./journeyNotes），只在快照与 W1 对齐后出现（主窗口 2026-09-24 定的最终顺序）。
 * 心愿排在驾校之后：收起时只显示一条，心愿是一挂好几天的常驻状态，驾校那一行多半是要主人动手的短期事（可以约考、领证仪式）；
 * 心愿在前会连着几天占住唯一那一条，把驾校的事压到“还有 N 条”后面（主窗口 2026-09-24 定）。
 *
 * 再加一种来源：
 * 1) 在 NOTE_KINDS 里按重要程度排一个位置；
 * 2) 写一个返回 PanelNote | null 的来源（照 ./schoolNote 的 useSchoolNote：只取服务端字段、取不到就返回 null）；
 * 3) 在 MapHomeView 里把它并进 arrangeNotes 的输入。排序、按宠物筛选与收起都不用改。
 */

export const NOTE_KINDS = ["mail", "listen", "trip", "school", "wish", "system"] as const;
export type NoteKind = (typeof NOTE_KINDS)[number];

export interface PanelNote {
  id: string;
  /** 来源种类，决定先后（见 NOTE_KINDS）。 */
  kind: NoteKind;
  text: string;
  to?: string;
  /** 只关于某一只宠物的提醒（例如驾校、旅行心愿）：面板显示的是别的宠物时不出现。 */
  petId?: string;
  /** 在地图上打开（例如 ?sheet=media:…）：不离开地图，不换当前宠物。 */
  onMap?: boolean;
}

/** 面板正在显示 petId 这只宠物时的提醒：去掉空的与只关于别的宠物的，按种类先后排（同一种保持原来的先后）。 */
export function arrangeNotes(notes: ReadonlyArray<PanelNote | null | undefined>, petId: string | null): PanelNote[] {
  const rank = (note: PanelNote) => NOTE_KINDS.indexOf(note.kind);
  return notes
    .filter((note): note is PanelNote => Boolean(note))
    .filter((note) => !note.petId || note.petId === petId)
    .map((note, index) => ({ note, index }))
    .sort((a, b) => rank(a.note) - rank(b.note) || a.index - b.index)
    .map(({ note }) => note);
}
