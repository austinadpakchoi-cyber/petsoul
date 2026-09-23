/**
 * 科二 / 科三的考局界面（也用于练习与比赛现场体验版）：
 * - 顶部约 10%：科目、项目、剩余时间、得分、暂停；中部约 60%：训练场画面；底部约 30%：操作区；
 * - 固定步长 30Hz 本地驾驶，约每秒上传一段操作，出现判定事件时立即上传，暂停 / 切后台时也上传；
 * - 服务端复算结果是准绳：对不上就按服务端记录重新同步；断线自动暂停，恢复后原样续传，不重新抽题、不抹掉扣分。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DriveItemProgress, InputChunk, InputResult, SchoolSession, SessionResult } from "@/shared/contracts";
import type { ApiError } from "@/shared/api/errors";
import { Button, Icon } from "@/shared/ui";
import type { Course, SimEventT, Snapshot } from "../sim/types";
import { formatTicks, reducedMotion } from "../text";
import { Controls, loadSteerMode, saveSteerMode, type SteerMode } from "./Controls";
import { DriveEngine, lerpPose, pose } from "./engine";
import { type Camera, draw, fitCamera, followCamera, type Palette, readPalette } from "./render";
import { Uploader } from "./uploader";

const TICK_MS = 1000 / 30;
const UPLOAD_EVERY = 30;

export interface DriveBackend {
  upload(chunk: InputChunk): Promise<InputResult>;
  pause(): Promise<unknown>;
  reload(): Promise<SchoolSession>;
}

export interface LocalItemSummary {
  item: string;
  title: string;
  status: string;
  events: SimEventT[];
  ticks: number;
}

type Phase = "ready" | "driving" | "paused" | "syncing" | "between" | "finished";

interface Toast {
  id: number;
  text: string;
  tone: "bad" | "good" | "info";
}

const CHECKS: [number, string][] = [
  [1, "系好安全带"],
  [2, "调好后视镜"],
  [3, "看看四周"],
];

function courseOf(item: DriveItemProgress): Course {
  return item.course as unknown as Course;
}

function snapshotOf(item: DriveItemProgress): Snapshot | null {
  return (item.snapshot as unknown as Snapshot | null) ?? null;
}

export function DriveRunner({
  title,
  items: initialItems,
  startIndex,
  practice,
  reasons,
  petLines,
  hints,
  backend,
  exitLabel,
  onExit,
  onFinished,
  onVoid,
}: {
  title: string;
  items: DriveItemProgress[];
  startIndex: number;
  practice: boolean;
  reasons: Record<string, string>;
  petLines: Record<string, string>;
  /** 练习提示（按项目） */
  hints: Record<string, string>;
  backend: DriveBackend | null;
  exitLabel: string;
  onExit: () => void;
  onFinished: (result: SessionResult | null, local: LocalItemSummary[]) => void;
  onVoid: (message: string) => void;
}) {
  const [items, setItems] = useState(initialItems);
  const [index, setIndex] = useState(startIndex);
  const [engine, setEngine] = useState(() => new DriveEngine(courseOf(initialItems[startIndex]), snapshotOf(initialItems[startIndex])));
  const [phase, setPhaseState] = useState<Phase>(() => (engine.tick > 0 ? "paused" : "ready"));
  const [version, setVersion] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [offline, setOffline] = useState(false);
  const [lost, setLost] = useState(false);
  const [invite, setInvite] = useState(false);
  const [notice, setNotice] = useState<string | null>(engine.tick > 0 ? "回来啦：按服务器保存的位置接着开。" : null);
  const [mode, setMode] = useState<SteerMode>(loadSteerMode);
  const [baseDeducted, setBaseDeducted] = useState(() =>
    initialItems.slice(0, startIndex).reduce((sum, it) => sum + it.sim_events.reduce((a, e) => a + e.p, 0), 0),
  );
  const phaseRef = useRef(phase);
  const engineRef = useRef(engine);
  const indexRef = useRef(index);
  const uploaderRef = useRef<Uploader | null>(null);
  const snapsRef = useRef(new Map<number, Snapshot>());
  const pressedRef = useRef<string | null>(null);
  const localRef = useRef<LocalItemSummary[]>([]);
  const toastSeq = useRef(0);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const paletteRef = useRef<Palette | null>(null);
  const finishedRef = useRef(false);
  const inviteRef = useRef(false);
  // 父组件传入的回调与文字放进 ref：循环和上传器只建一次，不因父组件重渲染而重建（否则会丢掉半个 tick 的累计时间与排队片段）。
  const live = useRef({ reasons, petLines, onFinished, onVoid, backend });
  live.current = { reasons, petLines, onFinished, onVoid, backend };
  const hasBackend = backend !== null;
  engineRef.current = engine;
  indexRef.current = index;

  const setPhase = useCallback((next: Phase) => {
    phaseRef.current = next;
    setPhaseState(next);
  }, []);

  const toast = useCallback((text: string, tone: Toast["tone"] = "info") => {
    const id = ++toastSeq.current;
    setToasts((list) => [...list.slice(-2), { id, text, tone }]);
    window.setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 2600);
  }, []);

  const finish = useCallback(
    (result: SessionResult | null) => {
      if (finishedRef.current) return;
      finishedRef.current = true;
      setPhase("finished");
      uploaderRef.current?.close();
      live.current.onFinished(result, localRef.current);
    },
    [setPhase],
  );

  const voided = useCallback(
    (message: string) => {
      if (finishedRef.current) return;
      finishedRef.current = true;
      setPhase("finished");
      uploaderRef.current?.close();
      live.current.onVoid(message);
    },
    [setPhase],
  );

  /** 按服务端记录重建（409 或快照对不上时）。 */
  const resyncFromServer = useCallback(async () => {
    const remote = live.current.backend;
    if (!remote) return;
    uploaderRef.current?.reset();
    snapsRef.current.clear();
    setPhase("syncing");
    try {
      const session = await remote.reload();
      if (session.state === "settled") return finish(session.result);
      if (session.state === "void") return voided("这场考局已经作废，不计次。");
      const drive = session.drive!;
      const current = drive.items[drive.current_item];
      setItems(drive.items);
      setIndex(drive.current_item);
      setBaseDeducted(drive.items.slice(0, drive.current_item).reduce((sum, it) => sum + it.sim_events.reduce((a, e) => a + e.p, 0), 0));
      const next = new DriveEngine(courseOf(current), snapshotOf(current));
      engineRef.current = next;
      setEngine(next);
      setNotice("已按服务器保存的记录对齐，点“继续”接着开。");
      setPhase(next.tick > 0 ? "paused" : "ready");
    } catch {
      // 连服务器记录都取不到：不让继续开（本地状态可能和服务器不一致），只提供“重新连接”。
      setLost(true);
      setNotice("暂时连不上服务器。重新连上后，会按服务器保存的位置和扣分接着开。");
      setPhase("paused");
      return;
    }
    setLost(false);
  }, [finish, voided, setPhase]);

  // 上传器：严格按顺序发送；每个考局实例一个。
  useEffect(() => {
    if (!hasBackend) return;
    const uploader = new Uploader((chunk) => live.current.backend!.upload(chunk), {
      result(result: InputResult, chunk: InputChunk) {
        const local = snapsRef.current.get(chunk.upto_tick);
        for (const key of [...snapsRef.current.keys()]) if (key <= chunk.upto_tick) snapsRef.current.delete(key);
        if (result.session_state === "settled") return finish(result.result);
        if (result.session_state === "void") return voided("这场考局已经作废，不计次。");
        const server = result.snapshot as unknown as Snapshot | null;
        if (chunk.item_index === indexRef.current && local && server && !DriveEngine.agrees(local, server)) {
          void resyncFromServer();
          return;
        }
        if (chunk.item_index === indexRef.current && result.item_status === "done" && result.current_item > chunk.item_index) {
          setBaseDeducted(result.deducted);
          setPhase("between");
        }
      },
      rejected(error: ApiError) {
        const reason = typeof error.details?.reason === "string" ? error.details.reason : "";
        if (reason === "platform_fault") return voided(error.message);
        void resyncFromServer();
      },
      offline(isOffline: boolean) {
        setOffline(isOffline);
        if (isOffline && phaseRef.current === "driving") {
          setPhase("paused");
          setNotice("信号中断了，已经自动暂停。恢复后会按原样补传，扣分和位置都会保留。");
        }
      },
    });
    uploaderRef.current = uploader;
    return () => {
      // 离开页面（包括开着车直接返回）：先把还没交出去的操作收成最后一段，再在后台按顺序发完，不丢刚发生的扣分；
      // 考局已结束时 finish / voided 已经 close，这里什么也不会发。
      const last = engineRef.current.takeChunk(indexRef.current);
      if (last) uploader.push(last);
      uploader.detach();
      uploaderRef.current = null;
    };
  }, [hasBackend, finish, voided, resyncFromServer, setPhase]);

  const flush = useCallback(() => {
    const eng = engineRef.current;
    const chunk = eng.takeChunk(indexRef.current);
    if (!chunk || !uploaderRef.current) return;
    snapsRef.current.set(chunk.upto_tick, eng.replay.snapshot());
    uploaderRef.current.push(chunk);
  }, []);

  const pause = useCallback(
    (why?: string) => {
      if (phaseRef.current !== "driving") return;
      setPhase("paused");
      if (why) setNotice(why);
      flush();
      void live.current.backend?.pause().catch(() => undefined);
    },
    [flush, setPhase],
  );

  const handleEvents = useCallback(
    (events: SimEventT[]) => {
      const { reasons: labels, petLines: lines } = live.current;
      for (const e of events) {
        if (e.k === "invite_shown") {
          inviteRef.current = true;
          setInvite(true);
          continue;
        }
        if (e.k === "line") pressedRef.current = e.ref;
        if (e.k === "done") {
          toast(lines.park ?? "停稳了。", "good");
          continue;
        }
        const text = labels[e.k] ?? e.k;
        if (e.f) toast(e.k === "timeout" || e.k === "out_of_bounds" ? `${text}，这一项结束了` : `红线：${text}，已自动制动`, "bad");
        else if (e.p > 0) toast(`${text} −${e.p}`, "bad");
      }
    },
    [toast],
  );

  // 固定步长循环 + 绘制
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    paletteRef.current = readPalette(canvas);
    const scheme = window.matchMedia?.("(prefers-color-scheme: dark)");
    const onScheme = () => (paletteRef.current = readPalette(canvas));
    scheme?.addEventListener?.("change", onScheme);
    const still = reducedMotion();
    let raf = 0;
    let last = performance.now();
    let acc = 0;
    let sinceUpload = 0;
    let sinceRender = 0;
    const loop = (now: number) => {
      const eng = engineRef.current;
      const dt = Math.min(250, now - last);
      last = now;
      if (phaseRef.current === "driving") {
        acc += dt;
        while (acc >= TICK_MS && eng.running) {
          acc -= TICK_MS;
          const events = eng.advance();
          sinceUpload += 1;
          sinceRender += 1;
          if (eng.replay.pressed === 0) pressedRef.current = null;
          if (events.length) {
            handleEvents(events);
            flush();
            sinceUpload = 0;
            setVersion((v) => v + 1);
          } else if (sinceUpload >= UPLOAD_EVERY) {
            flush();
            sinceUpload = 0;
          }
          if (inviteRef.current && eng.replay.r?.invite_done) {
            inviteRef.current = false;
            setInvite(false);
          }
        }
        if (sinceRender >= 6) {
          sinceRender = 0;
          setVersion((v) => v + 1);
        }
        if (!eng.running) {
          acc = 0;
          flush();
          const it = eng.course;
          localRef.current = [
            ...localRef.current.filter((s) => s.item !== it.item),
            { item: it.item, title: it.title, status: eng.replay.status, events: eng.replay.events, ticks: eng.tick },
          ];
          if (uploaderRef.current) setPhase("syncing");
          else finish(null);
        }
      } else {
        acc = 0;
      }
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const w = Math.max(1, Math.round(rect.width));
      const h = Math.max(1, Math.round(rect.height));
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const alpha = phaseRef.current === "driving" ? acc / TICK_MS : 1;
      const current = pose(eng.replay.car);
      const shown = alpha < 1 ? lerpPose(eng.prev, current, alpha) : current;
      const cam: Camera = eng.course.kind === "route" ? followCamera(shown, w, h) : fitCamera(eng.course.view, w, h);
      draw(ctx, w, h, cam, {
        course: eng.course,
        pose: shown,
        steer: eng.replay.car.s,
        gear: eng.replay.car.gear,
        brake: eng.brake,
        blink: eng.blink,
        tick: eng.tick,
        knocked: eng.replay.knocked,
        route: eng.replay.r,
        pressedLine: pressedRef.current,
        practice,
        predicted: practice && eng.running ? eng.predict(eng.course.kind === "route" ? 14 : 6) : null,
        blinkOn: still || Math.floor(now / 400) % 2 === 0,
      }, paletteRef.current!);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      scheme?.removeEventListener?.("change", onScheme);
    };
  }, [engine, finish, flush, handleEvents, practice, setPhase]);

  // 切后台、页面隐藏：自动暂停并上传
  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === "hidden") pause("切到后台时自动暂停了。");
    };
    const onOffline = () => pause("网络断开，已经自动暂停。");
    const onOnline = () => uploaderRef.current?.retryNow();
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("offline", onOffline);
    window.addEventListener("online", onOnline);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("online", onOnline);
    };
  }, [pause]);

  // 键盘：← → 转向，↑ 油门，空格 刹车，D / R 换挡，Q / E 转向灯，Esc 暂停
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (phaseRef.current !== "driving" || e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const eng = engineRef.current;
      const key = e.key.toLowerCase();
      if (key === "arrowleft") eng.nudgeSteer(1);
      else if (key === "arrowright") eng.nudgeSteer(-1);
      else if (key === "arrowup") eng.setThrottle(true);
      else if (key === " ") eng.setBrake(true);
      else if (key === "d" || key === "r") {
        if (!eng.shift(key === "d" ? 1 : -1) && eng.replay.car.v !== 0) toast("车还在动：先踩刹车停稳，再换挡。");
      } else if (key === "q") eng.setBlink(eng.blink === -1 ? 0 : -1);
      else if (key === "e") eng.setBlink(eng.blink === 1 ? 0 : 1);
      else if (key === "escape") pause();
      else return;
      e.preventDefault();
      setVersion((v) => v + 1);
    };
    const up = (e: KeyboardEvent) => {
      const eng = engineRef.current;
      if (e.key === "ArrowUp") eng.setThrottle(false);
      else if (e.key === " ") eng.setBrake(false);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [pause, toast]);

  const startDriving = () => {
    setNotice(null);
    setPhase("driving");
  };

  const nextItem = () => {
    const next = indexRef.current + 1;
    const item = items[next];
    if (!item) return;
    const eng = new DriveEngine(courseOf(item), null);
    engineRef.current = eng;
    snapsRef.current.clear();
    pressedRef.current = null;
    inviteRef.current = false;
    setInvite(false);
    setIndex(next);
    setEngine(eng);
    setPhase("ready");
  };

  const item = items[index];
  const course = engine.course;
  const route = course.route;
  const r = engine.replay.r;
  const score = Math.max(0, 100 - baseDeducted - engine.replay.deducted);
  const kmh = Math.round(Math.abs(engine.replay.car.v) * 30 * 3.6);
  const instruction = useMemo(() => {
    if (!route) return null;
    const [fx, fy] = engine.replay.front;
    const found = route.instructions.find((z) => {
      const xs = z.zone.map((p) => p[0]);
      const ys = z.zone.map((p) => p[1]);
      return fx >= Math.min(...xs) && fx <= Math.max(...xs) && fy >= Math.min(...ys) && fy <= Math.max(...ys);
    });
    return found?.text ?? null;
  }, [route, engine, version]); // version 驱动刷新：车的位置每 tick 都在变
  const holding = practice && course.target && engine.replay.hold > 0 ? engine.replay.hold / course.target.hold_ticks : 0;
  const hint = practice ? hints[course.item] ?? null : null;
  void version;

  return (
    <div className="ds-exam" data-tick={engine.tick} data-item={index}>
      <header className="ds-exam__top">
        <div className="ds-exam__title">
          <strong>{item.title}</strong>
          <span>
            {title}
            {items.length > 1 ? ` · 第 ${index + 1}/${items.length} 项` : ""}
          </span>
        </div>
        <div className="ds-exam__stat" aria-label="剩余时间">
          <span>剩余</span>
          <strong>{formatTicks(engine.limit - engine.tick)}</strong>
        </div>
        <div className="ds-exam__stat" aria-label={practice ? "练习得分（不计成绩）" : "当前得分"}>
          <span>{practice ? "练习分" : "得分"}</span>
          <strong>{score}</strong>
        </div>
        <Button variant="ghost" size="sm" icon="pause" aria-label="暂停" onClick={() => pause()} disabled={phase !== "driving"} />
      </header>

      <div className="ds-exam__field">
        <canvas ref={canvasRef} className="ds-canvas" role="img" aria-label={`${course.title}训练场：车速 ${kmh} 公里每小时，${engine.replay.car.gear === -1 ? "倒挡" : "前进挡"}`} />
        <div className="ds-field__hud">
          <span className="ds-badge">{engine.replay.car.gear === -1 ? "R 倒车" : "D 前进"}</span>
          <span className="ds-badge">{kmh} km/h</span>
          {route ? <span className="ds-badge">限速 {Math.round(route.speed_limit * 30 * 3.6)}</span> : null}
          {offline ? (
            <span className="ds-badge ds-badge--bad" role="status">
              <Icon name="alert" size={13} /> 信号中断，正在重试
            </span>
          ) : null}
        </div>
        {instruction ? <div className="ds-coach-line">龟教练：{instruction}</div> : null}
        {hint && !instruction ? <div className="ds-coach-line ds-coach-line--hint">提示：{hint}</div> : null}
        {holding > 0 ? (
          <div className="ds-hold" role="status">
            到位了，保持停稳 <progress max={1} value={holding} />
          </div>
        ) : null}
        <div className="ds-toasts" aria-live="polite">
          {toasts.map((t) => (
            <div key={t.id} className={`ds-toast ds-toast--${t.tone}`}>
              {t.text}
            </div>
          ))}
        </div>
        {route && r && !r.moved && phase === "driving" ? (
          <div className="ds-checks" role="group" aria-label="出发前检查">
            {CHECKS.map(([n, text]) => (
              <button
                key={n}
                type="button"
                className="ds-check"
                aria-pressed={r.checks.includes(n)}
                onClick={() => {
                  engine.check(n);
                  setVersion((v) => v + 1);
                }}
              >
                {r.checks.includes(n) ? "✓ " : ""}
                {text}
              </button>
            ))}
          </div>
        ) : null}
        {invite && phase === "driving" ? (
          <div className="ds-invite" role="alertdialog" aria-label="手机收到视频邀请">
            <div>
              <strong>视频邀请</strong>
              <p>朋友邀请你一起看新上的动画片。</p>
            </div>
            <div className="ps-row">
              <Button
                size="sm"
                variant="leaf"
                onClick={() => {
                  engine.invite(false);
                  inviteRef.current = false;
                  setInvite(false);
                }}
              >
                稍后再看
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  engine.invite(true);
                  inviteRef.current = false;
                  setInvite(false);
                  toast("开车时不看视频（考场不会真的打开视频）", "bad");
                }}
              >
                打开
              </Button>
            </div>
          </div>
        ) : null}

        {phase === "ready" ? (
          <div className="ds-overlay">
            <div className="ds-overlay__card">
              <strong className="ps-h2">{course.title}</strong>
              <p className="ps-muted">
                限时 {formatTicks(course.time_limit_ticks)}；{course.kind === "route" ? "按教练的指令开到星球食堂的装卸区，停稳 2 秒。" : course.kind === "curve" ? "沿车道开进终点区，停稳 1 秒。" : "整车停进车位、车身摆正，停稳 2 秒。"}
              </p>
              {hint ? <p className="ds-overlay__hint">{hint}</p> : null}
              <Button variant="primary" block onClick={startDriving}>
                {index === 0 ? "开始" : "开始这一项"}
              </Button>
            </div>
          </div>
        ) : null}
        {phase === "paused" ? (
          <div className="ds-overlay">
            <div className="ds-overlay__card">
              <strong className="ps-h2">已暂停</strong>
              {notice ? <p className="ps-muted">{notice}</p> : null}
              <p className="ps-muted">暂停不会重新抽题，也不会抹掉已经发生的扣分。</p>
              {lost ? (
                <Button variant="primary" block icon="refresh" onClick={() => void resyncFromServer()}>
                  重新连接
                </Button>
              ) : (
                <Button variant="primary" block disabled={offline} onClick={startDriving}>
                  {offline ? "等待信号恢复…" : "继续"}
                </Button>
              )}
              {offline && !lost ? (
                <Button block icon="refresh" onClick={() => uploaderRef.current?.retryNow()}>
                  现在重试
                </Button>
              ) : null}
              <Button variant="ghost" block onClick={onExit}>
                {exitLabel}
              </Button>
            </div>
          </div>
        ) : null}
        {phase === "syncing" ? (
          <div className="ds-overlay">
            <div className="ds-overlay__card" role="status">
              <strong className="ps-h2">{engine.replay.status === "done" ? "这一项完成了" : engine.replay.status === "failed" ? "这一项结束了" : "正在对齐记录"}</strong>
              <p className="ps-muted">{offline ? "信号中断，恢复后会自动补传。" : "正在请服务器复核这一段操作…"}</p>
            </div>
          </div>
        ) : null}
        {phase === "between" ? (
          <div className="ds-overlay">
            <div className="ds-overlay__card">
              <strong className="ps-h2">{item.title}完成！</strong>
              <p className="ps-muted">
                这一项扣 {engine.replay.deducted} 分。下一项：{items[index + 1]?.title}
              </p>
              <Button variant="primary" block onClick={nextItem}>
                开始下一项
              </Button>
            </div>
          </div>
        ) : null}
      </div>

      <div className="ds-exam__controls">
        <Controls
          engine={engine}
          mode={mode}
          onModeChange={(m) => {
            setMode(m);
            saveSteerMode(m);
          }}
          showBlinkers={!!route}
          version={version}
          onChange={() => setVersion((v) => v + 1)}
          onNotice={(text) => toast(text)}
        />
      </div>
    </div>
  );
}
