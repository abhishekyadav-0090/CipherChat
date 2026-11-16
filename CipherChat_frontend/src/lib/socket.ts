/**
 * WebSocket client for the CipherChat backend.
 *
 * Responsibilities, in the order they matter:
 *
 *  1. Correlate requests with responses. The protocol has no request IDs, so a
 *     request waits for its known reply type (see RESPONSE_FOR) and an `error`
 *     whose `request_type` matches.
 *  2. Survive a dead connection. Exponential backoff, jitter, and a keepalive
 *     that notices a half-open socket a browser would otherwise hide.
 *  3. Resume instead of re-authenticating. After a reconnect the stored session
 *     token is replayed, so the user is not asked for a password again.
 *
 * Deliberately framework-free: React lives in useChat, not here.
 */

import {
  RESPONSE_FOR,
  type ClientRequest,
  type ErrorCode,
  type ErrorResponse,
  type ServerFrame,
} from './protocol';

export type SocketState =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'ready'
  | 'reconnecting'
  | 'closed';

export class ProtocolError extends Error {
  readonly code: ErrorCode;
  readonly retryAfter?: number;

  constructor(code: ErrorCode, message: string, retryAfter?: number) {
    super(message);
    this.name = 'ProtocolError';
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

type Listener = (event: ServerFrame) => void;

interface PendingRequest {
  requestType: string;
  expect: string[];
  resolve: (value: ServerFrame) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

export interface ChatSocketOptions {
  url: string;
  /** Reconnect automatically when the socket drops. Default true. */
  autoReconnect?: boolean;
  /** Keepalive interval. The server drops idle connections at 300 s. */
  pingIntervalMs?: number;
  /** How long to wait for a reply before failing the request. */
  requestTimeoutMs?: number;
}

export class ChatSocket {
  readonly url: string;

  state: SocketState = 'idle';
  /** Session token, kept so a reconnect can resume rather than re-login. */
  token: string | null = null;

  private ws: WebSocket | null = null;
  private pending: PendingRequest[] = [];
  private listeners = new Map<string, Set<Listener>>();
  private stateListeners = new Set<(state: SocketState) => void>();
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private attempt = 0;
  private closedByUser = false;
  private lastPong = 0;

  private readonly autoReconnect: boolean;
  private readonly pingIntervalMs: number;
  private readonly requestTimeoutMs: number;

  constructor(options: ChatSocketOptions) {
    this.url = options.url;
    this.autoReconnect = options.autoReconnect ?? true;
    this.pingIntervalMs = options.pingIntervalMs ?? 25_000;
    this.requestTimeoutMs = options.requestTimeoutMs ?? 10_000;
  }

  /* ── connection ───────────────────────────────────────────────────────── */

  connect(): Promise<void> {
    if (this.ws && (this.state === 'connected' || this.state === 'ready')) {
      return Promise.resolve();
    }
    this.closedByUser = false;
    this.setState(this.attempt > 0 ? 'reconnecting' : 'connecting');

    return new Promise<void>((resolve, reject) => {
      let settled = false;
      let socket: WebSocket;

      try {
        socket = new WebSocket(this.url);
      } catch (error) {
        this.setState('closed');
        reject(error instanceof Error ? error : new Error('Could not open socket'));
        return;
      }

      this.ws = socket;

      socket.onopen = () => {
        settled = true;
        this.attempt = 0;
        this.setState('connected');
        this.startKeepalive();
        resolve();
      };

      socket.onmessage = (event: MessageEvent) => {
        this.handleFrame(event.data);
      };

      socket.onerror = () => {
        if (!settled) {
          settled = true;
          this.setState('closed');
          reject(new Error(`Cannot reach the server at ${this.url}`));
        }
      };

      socket.onclose = () => {
        this.stopKeepalive();
        this.failAllPending(new Error('Connection closed'));
        if (!settled) {
          settled = true;
          reject(new Error(`Cannot reach the server at ${this.url}`));
          return;
        }
        this.handleDisconnect();
      };
    });
  }

  close(): void {
    this.closedByUser = true;
    this.stopKeepalive();
    this.clearReconnectTimer();
    this.failAllPending(new Error('Client closed the connection'));
    const socket = this.ws;
    this.ws = null;
    if (socket) {
      socket.onclose = null;
      socket.onmessage = null;
      socket.onerror = null;
      try {
        socket.close();
      } catch {
        /* already gone */
      }
    }
    this.setState('closed');
  }

  /* ── requests ─────────────────────────────────────────────────────────── */

  request<T extends ServerFrame>(payload: ClientRequest): Promise<T> {
    const requestType = payload.type;
    const expect = RESPONSE_FOR[requestType] ?? [];

    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('Not connected'));
    }
    if (expect.length === 0) {
      // Fire-and-forget (typing, delivery_ack): send and resolve immediately.
      this.ws.send(JSON.stringify(payload));
      return Promise.resolve({ type: 'sent' } as unknown as T);
    }

    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending = this.pending.filter((item) => item.timer !== timer);
        reject(new Error(`No reply to ${requestType} within ${this.requestTimeoutMs}ms`));
      }, this.requestTimeoutMs);

      this.pending.push({
        requestType,
        expect,
        resolve: resolve as (value: ServerFrame) => void,
        reject,
        timer,
      });

      try {
        this.ws?.send(JSON.stringify(payload));
      } catch (error) {
        clearTimeout(timer);
        this.pending = this.pending.filter((item) => item.timer !== timer);
        reject(error instanceof Error ? error : new Error('Send failed'));
      }
    });
  }

  send(payload: ClientRequest): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  /* ── events ───────────────────────────────────────────────────────────── */

  /** Subscribe to a server event type, or '*' for every event. */
  on(eventType: string, listener: Listener): () => void {
    const set = this.listeners.get(eventType) ?? new Set<Listener>();
    set.add(listener);
    this.listeners.set(eventType, set);
    return () => {
      set.delete(listener);
    };
  }

  onStateChange(listener: (state: SocketState) => void): () => void {
    this.stateListeners.add(listener);
    return () => {
      this.stateListeners.delete(listener);
    };
  }

  /* ── internals ────────────────────────────────────────────────────────── */

  private handleFrame(raw: unknown): void {
    if (typeof raw !== 'string') return;

    let message: ServerFrame;
    try {
      message = JSON.parse(raw) as ServerFrame;
    } catch {
      return; // a frame we cannot parse is a frame we ignore
    }

    if (message.type === 'pong') {
      this.lastPong = Date.now();
    }

    // Resolve the oldest request that was waiting for this reply type.
    if (message.type === 'error') {
      const error = message as ErrorResponse;
      const index = this.pending.findIndex(
        (item) => item.requestType === error.request_type,
      );
      if (index >= 0) {
        const [pending] = this.pending.splice(index, 1);
        clearTimeout(pending.timer);
        pending.reject(new ProtocolError(error.code, error.message));
        return;
      }
    } else {
      const index = this.pending.findIndex((item) => item.expect.includes(message.type));
      if (index >= 0) {
        const [pending] = this.pending.splice(index, 1);
        clearTimeout(pending.timer);
        pending.resolve(message);
        return;
      }
    }

    this.emit(message);
  }

  private emit(message: ServerFrame): void {
    this.listeners.get(message.type)?.forEach((listener) => listener(message));
    this.listeners.get('*')?.forEach((listener) => listener(message));
  }

  private handleDisconnect(): void {
    this.ws = null;
    if (this.closedByUser || !this.autoReconnect) {
      this.setState('closed');
      return;
    }
    this.setState('reconnecting');
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    // 1 s, 2 s, 4 s, 8 s, then every 15 s, with jitter so a roomful of clients
    // does not reconnect in lockstep.
    const base = Math.min(1000 * 2 ** this.attempt, 15_000);
    const delay = base + Math.random() * 500;
    this.attempt += 1;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      void this.connect().catch(() => {
        this.scheduleReconnect();
      });
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private startKeepalive(): void {
    this.stopKeepalive();
    this.lastPong = Date.now();
    this.pingTimer = setInterval(() => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      // No pong for two intervals means the socket is half-open: the browser
      // still thinks it is connected, the server is long gone. Force a reconnect.
      if (Date.now() - this.lastPong > this.pingIntervalMs * 2) {
        try {
          this.ws.close();
        } catch {
          /* ignore */
        }
        return;
      }
      this.send({ type: 'ping' });
    }, this.pingIntervalMs);
  }

  private stopKeepalive(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private failAllPending(error: Error): void {
    const pending = this.pending;
    this.pending = [];
    pending.forEach((item) => {
      clearTimeout(item.timer);
      item.reject(error);
    });
  }

  private setState(state: SocketState): void {
    if (this.state === state) return;
    this.state = state;
    this.stateListeners.forEach((listener) => listener(state));
  }
}
