/**
 * 驾驶操作区（底部约 30%）：左手转向（方向盘或“左 / 右 + 回正”按钮），右手挡位、转向灯、刹车与油门。
 * 只改“期望控制”，由引擎在下一个 tick 记成操作事件；所有热区不小于 44px，相邻热区至少隔 10px。
 * 拇指区里只放开车要用的键：“转向方式”这种设置不放在操作区（开车时拇指一滑就会误切），
 * 改由考局的“开始”卡和暂停卡提供（SteerModeToggle）。
 * 手感与性能：
 * - 方向盘拖动时跟着手指连续转（直接改样式，不重渲染），挡位变了才告诉引擎；中心一小圈是死区（手指压在中心时角度乱跳）；
 * - 踏板、转向键按下只重渲染操作区，不再牵动整个考局页面；操作区用 stateKey 做 memo，父组件每 6 个 tick 刷新时没变就跳过。
 */
import { memo, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent } from "react";
import type { DriveEngine } from "./engine";

export type SteerMode = "wheel" | "buttons";

const MODE_KEY = "petsoul.school.steerMode";
/** 方向盘中心死区：离圆心不到半径的这个比例时，手指移动不算转动。 */
export const WHEEL_DEAD_ZONE = 0.22;
/**
 * 界面层“方向盘角度 → 转向档位”的换算：每 10° 一档，12 档满舵是 120°（原来每 15° 一档、满舵要转半圈，
 * 390 宽下指尖要走约 160px 的弧，来回修方向会累；巡检第二轮触屏实测 P2）。只改界面换算，档位数与车辆参数仍来自场地配置。
 */
export const WHEEL_DEG_PER_STEP = 10;

export function loadSteerMode(): SteerMode {
  try {
    return window.localStorage.getItem(MODE_KEY) === "buttons" ? "buttons" : "wheel";
  } catch {
    return "wheel";
  }
}

export function saveSteerMode(mode: SteerMode): void {
  try {
    window.localStorage.setItem(MODE_KEY, mode);
  } catch {
    /* 隐私模式下不记住偏好 */
  }
}

/** 转向状态的说法（读屏与方向表共用）：正数向左、负数向右。 */
export function steerText(target: number): string {
  return target === 0 ? "回正" : target > 0 ? `向左 ${target} 档` : `向右 ${-target} 档`;
}

/** 转向方式切换（方向盘 / 按钮）：放在“开始”卡和暂停卡里，不放在拇指区。 */
export function SteerModeToggle({ mode, onModeChange }: { mode: SteerMode; onModeChange: (mode: SteerMode) => void }) {
  return (
    <div className="ds-steer-mode">
      <span className="ds-steer-mode__label">转向方式</span>
      <div className="ds-segmented" role="group" aria-label="转向方式">
        <button type="button" aria-pressed={mode === "wheel"} onClick={() => onModeChange("wheel")}>
          方向盘
        </button>
        <button type="button" aria-pressed={mode === "buttons"} onClick={() => onModeChange("buttons")}>
          按钮
        </button>
      </div>
    </div>
  );
}

/** 按住重复：按下立即执行一次，0.2 秒后每 66ms 重复，松开停止。 */
function useRepeat(action: () => void) {
  const timer = useRef<number | null>(null);
  const stop = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  };
  const start = () => {
    stop();
    action();
    const loop = (delay: number) => {
      timer.current = window.setTimeout(() => {
        action();
        loop(66);
      }, delay);
    };
    loop(200);
  };
  useEffect(() => stop, []);
  return { start, stop };
}

function SteerButtons({ engine, onSteer }: { engine: DriveEngine; onSteer: () => void }) {
  const [held, setHeld] = useState<-1 | 0 | 1>(0);
  const left = useRepeat(() => {
    engine.nudgeSteer(1);
    onSteer();
  });
  const right = useRepeat(() => {
    engine.nudgeSteer(-1);
    onSteer();
  });
  const bind = (side: -1 | 1, r: { start: () => void; stop: () => void }) => {
    const release = () => {
      r.stop();
      setHeld(0);
    };
    return {
      "data-held": held === side ? "" : undefined,
      onPointerDown: (e: ReactPointerEvent) => {
        e.preventDefault();
        (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
        setHeld(side);
        r.start();
      },
      onPointerUp: release,
      onPointerCancel: release,
      onLostPointerCapture: release,
      onContextMenu: (e: ReactMouseEvent) => e.preventDefault(),
    };
  };
  const steps = engine.course.car.steer_steps;
  const target = engine.steerTarget;
  // 左、右两个大键并排（按住持续转），“回正”单独一行放在下面：不和左右键挤在同一排，免得想转向时误点回正。
  // 上面一条方向表：按钮模式看不到方向盘，打了几档要一眼看到。
  return (
    <div className="ds-steer-buttons" role="group" aria-label="转向">
      <div className="ds-steer-meter" role="img" aria-label={`方向：${steerText(target)}`} style={{ ["--pos" as string]: String(0.5 - target / (2 * steps)) }}>
        <span />
      </div>
      <button type="button" className="ds-key" aria-label="向左转（按住持续转）" aria-keyshortcuts="ArrowLeft" {...bind(1, left)}>
        ◀ 左
      </button>
      <button type="button" className="ds-key" aria-label="向右转（按住持续转）" aria-keyshortcuts="ArrowRight" {...bind(-1, right)}>
        右 ▶
      </button>
      <button
        type="button"
        className="ds-key ds-key--soft ds-key--center"
        onClick={() => {
          engine.setSteer(0);
          onSteer();
        }}
      >
        回正
      </button>
    </div>
  );
}

/** 方向盘：拖动旋转，松手停在原处；每 10° 一档，满舵 ±120°。拖动中跟着手指连续转，松手后转到所在的那一档。 */
function SteerWheel({ engine, onSteer }: { engine: DriveEngine; onSteer: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<{ last: number | null; acc: number } | null>(null);
  const steps = engine.course.car.steer_steps;
  const degPerStep = WHEEL_DEG_PER_STEP;
  const lock = steps * degPerStep;
  const target = engine.steerTarget;
  const stepAngle = -target * degPerStep;
  const shown = drag.current ? drag.current.acc : stepAngle;
  const polar = (e: ReactPointerEvent) => {
    const rect = ref.current!.getBoundingClientRect();
    const dx = e.clientX - (rect.left + rect.width / 2);
    const dy = e.clientY - (rect.top + rect.height / 2);
    return { angle: (Math.atan2(dy, dx) * 180) / Math.PI, inside: Math.hypot(dx, dy) < (rect.width / 2) * WHEEL_DEAD_ZONE };
  };
  const end = () => {
    if (!drag.current) return;
    drag.current = null;
    ref.current?.classList.remove("is-dragging");
    onSteer();
  };
  return (
    <div className="ds-wheel-wrap">
      <div
        ref={ref}
        className={`ds-wheel${drag.current ? " is-dragging" : ""}`}
        role="slider"
        tabIndex={0}
        aria-label="方向盘"
        aria-keyshortcuts="ArrowLeft ArrowRight"
        aria-valuemin={-steps}
        aria-valuemax={steps}
        aria-valuenow={-target}
        aria-valuetext={steerText(target)}
        style={{ transform: `rotate(${shown}deg)` }}
        onPointerDown={(e) => {
          e.preventDefault();
          e.currentTarget.setPointerCapture?.(e.pointerId);
          const p = polar(e);
          drag.current = { last: p.inside ? null : p.angle, acc: stepAngle };
          e.currentTarget.classList.add("is-dragging");
        }}
        onPointerMove={(e) => {
          const d = drag.current;
          if (!d) return;
          const p = polar(e);
          // 死区里不转，也不记起点：手指从中心穿过去不会让方向盘猛地跳半圈
          if (p.inside) {
            d.last = null;
            return;
          }
          if (d.last === null) {
            d.last = p.angle;
            return;
          }
          let delta = p.angle - d.last;
          if (delta > 180) delta -= 360;
          if (delta < -180) delta += 360;
          d.last = p.angle;
          d.acc = Math.max(-lock, Math.min(lock, d.acc + delta));
          const el = e.currentTarget;
          el.style.transform = `rotate(${d.acc}deg)`;
          const next = -Math.round(d.acc / degPerStep);
          if (next !== engine.steerTarget) {
            engine.setSteer(next);
            el.setAttribute("aria-valuenow", String(-engine.steerTarget));
            el.setAttribute("aria-valuetext", steerText(engine.steerTarget));
          }
        }}
        onPointerUp={end}
        onPointerCancel={end}
        onLostPointerCapture={end}
        onContextMenu={(e) => e.preventDefault()}
      >
        <svg viewBox="0 0 100 100" aria-hidden="true">
          <circle cx="50" cy="50" r="44" className="ds-wheel__rim" />
          <circle cx="50" cy="50" r="12" className="ds-wheel__hub" />
          <path d="M50 38 V8 M38 54 L10 66 M62 54 L90 66" className="ds-wheel__spoke" />
          <circle cx="50" cy="8" r="4" className="ds-wheel__mark" />
        </svg>
      </div>
      <button
        type="button"
        className="ds-key ds-key--soft ds-wheel__center"
        onClick={() => {
          engine.setSteer(0);
          onSteer();
        }}
      >
        回正
      </button>
    </div>
  );
}

function Pedal({ label, name, tone, active, keys, onPress }: { label: string; name: string; tone: "brake" | "gas"; active: boolean; keys: string; onPress: (on: boolean) => void }) {
  return (
    <button
      type="button"
      className={`ds-pedal ds-pedal--${tone}${active ? " is-active" : ""}`}
      aria-label={name}
      aria-pressed={active}
      aria-keyshortcuts={keys}
      onPointerDown={(e) => {
        e.preventDefault();
        e.currentTarget.setPointerCapture?.(e.pointerId);
        onPress(true);
      }}
      onPointerUp={() => onPress(false)}
      onPointerCancel={() => onPress(false)}
      onLostPointerCapture={() => onPress(false)}
      onKeyDown={(e) => {
        if (e.key === "Enter") onPress(true);
      }}
      onKeyUp={(e) => {
        if (e.key === "Enter") onPress(false);
      }}
      onContextMenu={(e) => e.preventDefault()}
    >
      {label}
    </button>
  );
}

/** 父组件每次渲染都算一次：只有这些变了，操作区才需要重渲染。 */
export function controlsKey(engine: DriveEngine): string {
  const car = engine.replay.car;
  return `${car.gear}|${car.v === 0 ? 1 : 0}|${engine.steerTarget}|${engine.blink}|${engine.brake ? 1 : 0}|${engine.throttle ? 1 : 0}`;
}

function ControlsImpl({
  engine,
  mode,
  showBlinkers,
  stateKey,
  onNotice,
}: {
  engine: DriveEngine;
  mode: SteerMode;
  showBlinkers: boolean;
  /** controlsKey(engine)：只用来让 memo 知道要不要重渲染，渲染时一律直接读引擎 */
  stateKey: string;
  onNotice: (text: string) => void;
}) {
  const [, force] = useState(0);
  // 操作区自己的按键只重渲染操作区：画面每帧直接读引擎，顶栏每 6 个 tick 自己刷新
  const changed = () => force((n) => n + 1);
  const car = engine.replay.car;
  const stopped = car.v === 0;
  const shift = (gear: 1 | -1) => {
    if (car.gear === gear) return;
    if (!stopped) {
      onNotice("车还在动：先踩刹车停稳，再换挡。");
      return;
    }
    engine.shift(gear);
    changed();
  };
  void stateKey;
  const blink = (side: -1 | 1) => {
    engine.setBlink(engine.blink === side ? 0 : side);
    changed();
  };
  return (
    <div className="ds-controls">
      <div className="ds-controls__left">
        {mode === "wheel" ? <SteerWheel engine={engine} onSteer={changed} /> : <SteerButtons engine={engine} onSteer={changed} />}
      </div>
      <div className="ds-controls__right">
        {/* 挡位只放 D、R 两个键；转向灯另起一行（四个挤一排时 320 宽会被挤出屏幕、每个不到 44px）。 */}
        <div className="ds-gears" role="group" aria-label={stopped ? "挡位" : "挡位（停稳后才能切换）"}>
          <button type="button" className="ds-gear" aria-label="D 前进挡" aria-keyshortcuts="D" aria-pressed={car.gear === 1} aria-disabled={!stopped} onClick={() => shift(1)}>
            D
          </button>
          <button type="button" className="ds-gear" aria-label="R 倒车挡" aria-keyshortcuts="R" aria-pressed={car.gear === -1} aria-disabled={!stopped} onClick={() => shift(-1)}>
            R
          </button>
        </div>
        {showBlinkers ? (
          <div className="ds-gears ds-blinkers" role="group" aria-label="转向灯">
            <button type="button" className="ds-gear ds-gear--blink" aria-label="左转向灯" aria-keyshortcuts="Q" aria-pressed={engine.blink === -1} onClick={() => blink(-1)}>
              ◀ 左灯
            </button>
            <button type="button" className="ds-gear ds-gear--blink" aria-label="右转向灯" aria-keyshortcuts="E" aria-pressed={engine.blink === 1} onClick={() => blink(1)}>
              右灯 ▶
            </button>
          </div>
        ) : null}
        <div className="ds-pedals">
          <Pedal
            label="刹车"
            name="刹车"
            tone="brake"
            keys="Space ArrowDown"
            active={engine.brake}
            onPress={(on) => {
              engine.setBrake(on);
              changed();
            }}
          />
          <Pedal
            label={car.gear === -1 ? "油门（倒）" : "油门"}
            name={car.gear === -1 ? "油门（倒车）" : "油门"}
            tone="gas"
            keys="ArrowUp"
            active={engine.throttle}
            onPress={(on) => {
              engine.setThrottle(on);
              changed();
            }}
          />
        </div>
      </div>
    </div>
  );
}

export const Controls = memo(ControlsImpl);
