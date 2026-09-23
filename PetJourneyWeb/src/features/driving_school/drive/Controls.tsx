/**
 * 驾驶操作区（底部约 30%）：左手转向（方向盘或“左 / 回正 / 右”按钮），右手刹车与油门，停稳后切 D / R，转向灯。
 * 只改“期望控制”，由引擎在下一个 tick 记成操作事件；所有热区不小于 44px。
 */
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import type { DriveEngine } from "./engine";

export type SteerMode = "wheel" | "buttons";

const MODE_KEY = "petsoul.school.steerMode";

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

function SteerButtons({ engine, onChange }: { engine: DriveEngine; onChange: () => void }) {
  const left = useRepeat(() => {
    engine.nudgeSteer(1);
    onChange();
  });
  const right = useRepeat(() => {
    engine.nudgeSteer(-1);
    onChange();
  });
  const bind = (r: { start: () => void; stop: () => void }) => ({
    onPointerDown: (e: ReactPointerEvent) => {
      e.preventDefault();
      (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
      r.start();
    },
    onPointerUp: r.stop,
    onPointerCancel: r.stop,
    onLostPointerCapture: r.stop,
  });
  return (
    <div className="ds-steer-buttons" role="group" aria-label="转向">
      <button type="button" className="ds-key" aria-label="向左转（按住持续转）" {...bind(left)}>
        ◀ 左
      </button>
      <button
        type="button"
        className="ds-key ds-key--soft"
        onClick={() => {
          engine.setSteer(0);
          onChange();
        }}
      >
        回正
      </button>
      <button type="button" className="ds-key" aria-label="向右转（按住持续转）" {...bind(right)}>
        右 ▶
      </button>
    </div>
  );
}

/** 方向盘：拖动旋转，松手停在原处；每 15° 一档，满舵 ±180°。 */
function SteerWheel({ engine, onChange }: { engine: DriveEngine; onChange: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<{ last: number; acc: number } | null>(null);
  const steps = engine.course.car.steer_steps;
  const degPerStep = 180 / steps;
  const angleOf = (e: ReactPointerEvent) => {
    const rect = ref.current!.getBoundingClientRect();
    return (Math.atan2(e.clientY - (rect.top + rect.height / 2), e.clientX - (rect.left + rect.width / 2)) * 180) / Math.PI;
  };
  const rotation = -engine.steerTarget * degPerStep;
  return (
    <div className="ds-wheel-wrap">
      <div
        ref={ref}
        className="ds-wheel"
        role="slider"
        tabIndex={0}
        aria-label="方向盘"
        aria-valuemin={-steps}
        aria-valuemax={steps}
        aria-valuenow={-engine.steerTarget}
        aria-valuetext={engine.steerTarget === 0 ? "回正" : engine.steerTarget > 0 ? `向左 ${engine.steerTarget} 档` : `向右 ${-engine.steerTarget} 档`}
        style={{ transform: `rotate(${rotation}deg)` }}
        onPointerDown={(e) => {
          e.preventDefault();
          e.currentTarget.setPointerCapture?.(e.pointerId);
          drag.current = { last: angleOf(e), acc: rotation };
        }}
        onPointerMove={(e) => {
          const d = drag.current;
          if (!d) return;
          const a = angleOf(e);
          let delta = a - d.last;
          if (delta > 180) delta -= 360;
          if (delta < -180) delta += 360;
          d.last = a;
          d.acc = Math.max(-180, Math.min(180, d.acc + delta));
          const target = -Math.round(d.acc / degPerStep);
          if (target !== engine.steerTarget) {
            engine.setSteer(target);
            onChange();
          }
        }}
        onPointerUp={() => (drag.current = null)}
        onPointerCancel={() => (drag.current = null)}
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
          onChange();
        }}
      >
        回正
      </button>
    </div>
  );
}

function Pedal({ label, tone, active, onPress }: { label: string; tone: "brake" | "gas"; active: boolean; onPress: (on: boolean) => void }) {
  return (
    <button
      type="button"
      className={`ds-pedal ds-pedal--${tone}${active ? " is-active" : ""}`}
      aria-pressed={active}
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

export function Controls({
  engine,
  mode,
  onModeChange,
  showBlinkers,
  version,
  onChange,
  onNotice,
}: {
  engine: DriveEngine;
  mode: SteerMode;
  onModeChange: (mode: SteerMode) => void;
  showBlinkers: boolean;
  /** 父组件每个 tick 递增，驱动挡位与速度显示刷新 */
  version: number;
  onChange: () => void;
  onNotice: (text: string) => void;
}) {
  const [, force] = useState(0);
  const changed = () => {
    force((n) => n + 1);
    onChange();
  };
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
  void version;
  return (
    <div className="ds-controls">
      <div className="ds-controls__left">
        {mode === "wheel" ? <SteerWheel engine={engine} onChange={changed} /> : <SteerButtons engine={engine} onChange={changed} />}
        <div className="ds-segmented" role="group" aria-label="转向方式">
          <button type="button" aria-pressed={mode === "wheel"} onClick={() => onModeChange("wheel")}>
            方向盘
          </button>
          <button type="button" aria-pressed={mode === "buttons"} onClick={() => onModeChange("buttons")}>
            按钮
          </button>
        </div>
      </div>
      <div className="ds-controls__right">
        <div className="ds-gears" role="group" aria-label={stopped ? "挡位" : "挡位（停稳后才能切换）"}>
          <button type="button" className="ds-gear" aria-pressed={car.gear === 1} aria-disabled={!stopped} onClick={() => shift(1)}>
            D
          </button>
          <button type="button" className="ds-gear" aria-pressed={car.gear === -1} aria-disabled={!stopped} onClick={() => shift(-1)}>
            R
          </button>
          {showBlinkers ? (
            <>
              <button
                type="button"
                className="ds-gear ds-gear--blink"
                aria-label="左转向灯"
                aria-pressed={engine.blink === -1}
                onClick={() => {
                  engine.setBlink(engine.blink === -1 ? 0 : -1);
                  changed();
                }}
              >
                ◀灯
              </button>
              <button
                type="button"
                className="ds-gear ds-gear--blink"
                aria-label="右转向灯"
                aria-pressed={engine.blink === 1}
                onClick={() => {
                  engine.setBlink(engine.blink === 1 ? 0 : 1);
                  changed();
                }}
              >
                灯▶
              </button>
            </>
          ) : null}
        </div>
        <div className="ds-pedals">
          <Pedal
            label="刹车"
            tone="brake"
            active={engine.brake}
            onPress={(on) => {
              engine.setBrake(on);
              changed();
            }}
          />
          <Pedal
            label={car.gear === -1 ? "油门（倒）" : "油门"}
            tone="gas"
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
