/**
 * 操作片段上传器：严格按顺序一段一段发；网络失败原样重发同一段（服务端对完全相同的重发原样返回，天然幂等）；
 * 服务端拒绝（409 不连续 / 不一致 / 考局已结束 / 平台故障）时清空队列交给调用方按服务端记录重新同步。
 * 离开考场（组件卸载）时调用 detach：不再回调页面，但把已经排队的片段发完——马上离开不会丢掉刚发生的操作和扣分。
 */
import type { InputChunk, InputResult } from "@/shared/contracts";
import { type ApiError, toApiError } from "@/shared/api/errors";

export interface UploaderEvents {
  result: (result: InputResult, chunk: InputChunk) => void;
  rejected: (error: ApiError, chunk: InputChunk) => void;
  offline: (offline: boolean) => void;
}

const QUIET: UploaderEvents = { result: () => undefined, rejected: () => undefined, offline: () => undefined };
const DETACHED_RETRIES = 5;

export class Uploader {
  private queue: InputChunk[] = [];
  private busy = false;
  private failures = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;
  private detached = false;

  constructor(
    private readonly send: (chunk: InputChunk) => Promise<InputResult>,
    private on: UploaderEvents,
  ) {}

  get idle(): boolean {
    return !this.busy && this.queue.length === 0;
  }

  get offline(): boolean {
    return this.failures > 0;
  }

  push(chunk: InputChunk): void {
    if (this.closed) return;
    this.queue.push(chunk);
    void this.pump();
  }

  /** 放弃排队中的片段（重新同步前调用）。 */
  reset(): void {
    this.queue = [];
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.failures = 0;
  }

  /** 考局已结束：丢弃排队（服务端已结算或作废，不再接受操作）。 */
  close(): void {
    this.closed = true;
    this.reset();
  }

  /** 页面离开：不再回调，但把排队的片段按顺序发完（网络失败时有限次重试）。 */
  detach(): void {
    this.detached = true;
    this.on = QUIET;
    void this.pump();
  }

  /** 立即重试（例如网络恢复时）。 */
  retryNow(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
      this.busy = false;
    }
    void this.pump();
  }

  private async pump(): Promise<void> {
    if (this.busy || this.closed) return;
    const chunk = this.queue[0];
    if (!chunk) return;
    this.busy = true;
    try {
      const result = await this.send(chunk);
      if (this.closed || this.queue[0] !== chunk) {
        this.busy = false;
        return;
      }
      this.queue.shift();
      if (this.failures > 0) {
        this.failures = 0;
        this.on.offline(false);
      }
      this.busy = false;
      this.on.result(result, chunk);
    } catch (raw) {
      const error = toApiError(raw);
      if (this.closed || this.queue[0] !== chunk) {
        this.busy = false;
        return;
      }
      const transient = error.kind === "network" || error.kind === "timeout" || (error.status !== null && error.status >= 500) || error.code === "RATE_LIMITED";
      if (transient && !(this.detached && this.failures >= DETACHED_RETRIES)) {
        this.failures += 1;
        if (this.failures === 1) this.on.offline(true);
        const wait = Math.min(8000, 1000 * 2 ** (this.failures - 1));
        this.timer = setTimeout(() => {
          this.timer = null;
          this.busy = false;
          void this.pump();
        }, wait);
        return;
      }
      this.queue = [];
      this.busy = false;
      this.failures = 0;
      this.on.rejected(error, chunk);
      return;
    }
    void this.pump();
  }
}
