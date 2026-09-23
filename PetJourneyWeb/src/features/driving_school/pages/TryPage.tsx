/**
 * /school/try（全屏）：比赛现场用的“倒车入库体验版”。
 * 只在本机运行同一套确定性模拟，不连后端、不计成绩、不发证、不消耗任何考试机会。
 */
import { useMemo, useState } from "react";
import { Link } from "react-router";
import type { DriveItemProgress } from "@/shared/contracts";
import { Button, Card, Chip, Page } from "@/shared/ui";
import { DEMO_CURRICULUM, demoCourse } from "@/fixtures/driving";
import { DriveRunner, type LocalItemSummary } from "../drive/DriveRunner";
import { practiceHints } from "../hooks";

function freshItem(): DriveItemProgress {
  const course = demoCourse("reverse_park", "a");
  return { item: "reverse_park", title: course.title, course: course as unknown as Record<string, unknown>, status: "running", committed_tick: 0, events: [], sim_events: [], snapshot: null };
}

export function TryPage() {
  const [round, setRound] = useState(0);
  const [outcome, setOutcome] = useState<LocalItemSummary | null>(null);
  // round 变化时换一局新的场地状态
  const items = useMemo(() => (round >= 0 ? [freshItem()] : []), [round]);
  const hints = useMemo(() => practiceHints(DEMO_CURRICULUM), []);
  const lines = DEMO_CURRICULUM.pet_lines.lively;

  if (outcome) {
    const deducted = outcome.events.reduce((sum, e) => sum + e.p, 0);
    const fatal = outcome.events.find((e) => e.f);
    const done = outcome.status === "done";
    return (
      <Page bare className="ds-prepare">
        <div className="ps-stack">
          <Chip tone="sky">体验版 · 不计成绩、不发证</Chip>
          <h1 className="ps-h1">{done ? "停进去啦！" : "这次没停进去"}</h1>
          <Card className={`ds-score ${done ? "is-pass" : "is-fail"}`}>
            <div className="ds-score__num">
              <strong>{done ? Math.max(0, 100 - deducted) : 0}</strong>
              <span>/ 100</span>
            </div>
            <span className="ps-muted">{fatal ? DEMO_CURRICULUM.reasons[fatal.k] ?? fatal.k : deducted ? `扣了 ${deducted} 分` : "一分没扣"}</span>
          </Card>
          <ul className="ds-list">
            {outcome.events
              .filter((e) => e.p > 0)
              .map((e, i) => (
                <li key={i}>
                  {DEMO_CURRICULUM.reasons[e.k] ?? e.k} −{e.p}
                </li>
              ))}
          </ul>
          <p className="ps-muted">正式的爪爪驾校有四个科目：科目二里倒车入库、侧方停车、弯道行驶连着考。陪 TA 报名后可以不限次数地练习。</p>
          <Button
            variant="primary"
            block
            onClick={() => {
              setOutcome(null);
              setRound(round + 1);
            }}
          >
            再来一次
          </Button>
          <Link className="ps-btn ps-btn--secondary ps-btn--block" to="/school">
            去爪爪驾校
          </Link>
        </div>
      </Page>
    );
  }

  return (
    <div className="ds-session">
      <DriveRunner
        key={round}
        title="体验版 · 不计成绩"
        items={items}
        startIndex={0}
        practice
        reasons={DEMO_CURRICULUM.reasons}
        petLines={lines}
        hints={hints}
        backend={null}
        exitLabel="重新开始"
        onExit={() => setRound(round + 1)}
        onFinished={(_result, local) => setOutcome(local[0] ?? null)}
        onVoid={() => undefined}
      />
    </div>
  );
}
