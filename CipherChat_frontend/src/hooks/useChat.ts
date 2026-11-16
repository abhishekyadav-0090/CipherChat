/**
 * useChat — the entire backend integration for the app.
 *
 * Design rules this hook enforces:
 *
 *  1. The server decides identity and delivery. The UI never invents a status;
 *     it renders what the server confirmed.
 *  2. `stored` is success, not failure — the recipient is offline and the
 *     message will be replayed at their next login.
 *  3. Nothing secret is persisted in a way that outlives the tab: the session
 *     token lives in memory and in sessionStorage (cleared when the tab closes),
 *     never in localStorage.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ERROR_TEXT,
  type ErrorCode,
  type GroupsResponse,
  type HistoryResponse,
  type IncomingGroupMessageEvent,
  type IncomingMessageEvent,
  type LoginResponse,
  type MessageResponse,
  type PresenceEvent,
  type ProtocolUser,
  type RegisterResponse,
  type ResumeResponse,
  type ServerInfoResponse,
  type TypingEvent,
  type UsersResponse,
} from '../lib/protocol';
import { ChatSocket, ProtocolError, type SocketState } from '../lib/socket';

export type MessageStatus = 'sending' | 'sent' | 'delivered' | 'read' | 'failed';

export interface ChatMessage {
  id: string;
  serverId: number | null;
  chatId: string;
  senderId: number;
  senderName: string;
  body: string;
  at: string;
  status: MessageStatus;
  mine: boolean;
}

export interface Chat {
  id: string;
  kind: 'dm' | 'group';
  title: string;
  peerId?: number;
  groupId?: number;
  online: boolean;
  lastSeen: string | null;
  members: string[];
  lastMessage?: ChatMessage;
  unread: number;
  typing: boolean;
}

export interface Session {
  userId: number;
  username: string;
  token: string;
  expiresAt?: string;
}

export interface AuthError {
  code?: ErrorCode;
  message: string;
  retryAfter?: number;
}

export interface Notice {
  id: string;
  title: string;
  body?: string;
  tone: 'info' | 'success' | 'error';
}

export const dmChatId = (userId: number) => `dm-${userId}`;
export const groupChatId = (groupId: number) => `grp-${groupId}`;

const SESSION_KEY = 'cipherchat.session';
const SERVER_URL =
  (import.meta.env?.VITE_SERVER_URL as string | undefined) ?? 'wss://localhost:5443';

/** Read the tab-scoped session, if the tab was reloaded. */
function readStoredSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Session;
    if (!parsed?.token || typeof parsed.userId !== 'number') return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeStoredSession(session: Session | null): void {
  try {
    if (session) sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    else sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* private mode — memory only is fine */
  }
}

function toAuthError(error: unknown): AuthError {
  if (error instanceof ProtocolError) {
    return {
      code: error.code,
      message: ERROR_TEXT[error.code] ?? error.message,
      retryAfter: error.retryAfter,
    };
  }
  if (error instanceof Error) return { message: error.message };
  return { message: 'Something went wrong' };
}

export function useChat() {
  const socketRef = useRef<ChatSocket | null>(null);
  const sessionRef = useRef<Session | null>(null);
  const activeChatRef = useRef<string>('');
  const namesRef = useRef<Map<number, string>>(new Map());

  const [status, setStatus] = useState<SocketState>('idle');
  const [session, setSession] = useState<Session | null>(null);
  const [authError, setAuthError] = useState<AuthError | null>(null);
  const [busy, setBusy] = useState(false);
  const [users, setUsers] = useState<ProtocolUser[]>([]);
  const [groups, setGroups] = useState<GroupsResponse['groups']>([]);
  const [messages, setMessages] = useState<Record<string, ChatMessage[]>>({});
  const [unread, setUnread] = useState<Record<string, number>>({});
  const [typing, setTyping] = useState<Record<string, boolean>>({});
  const [activeChatId, setActiveChatId] = useState('');
  const [notices, setNotices] = useState<Notice[]>([]);
  const [serverInfo, setServerInfo] = useState<ServerInfoResponse | null>(null);

  /* ── notices ──────────────────────────────────────────────────────────── */

  const notify = useCallback((title: string, body?: string, tone: Notice['tone'] = 'info') => {
    const id = Math.random().toString(36).slice(2, 9);
    setNotices((prev) => [...prev.slice(-3), { id, title, body, tone }]);
    window.setTimeout(() => {
      setNotices((prev) => prev.filter((notice) => notice.id !== id));
    }, 4200);
  }, []);

  const dismissNotice = useCallback((id: string) => {
    setNotices((prev) => prev.filter((notice) => notice.id !== id));
  }, []);

  /* ── helpers ──────────────────────────────────────────────────────────── */

  const appendMessage = useCallback((message: ChatMessage) => {
    setMessages((prev) => {
      const thread = prev[message.chatId] ?? [];
      if (thread.some((existing) => existing.id === message.id)) return prev;
      return { ...prev, [message.chatId]: [...thread, message] };
    });
  }, []);

  const patchMessage = useCallback(
    (chatId: string, predicate: (message: ChatMessage) => boolean, patch: Partial<ChatMessage>) => {
      setMessages((prev) => {
        const thread = prev[chatId];
        if (!thread) return prev;
        let changed = false;
        const next = thread.map((message) => {
          if (!predicate(message)) return message;
          changed = true;
          return { ...message, ...patch };
        });
        return changed ? { ...prev, [chatId]: next } : prev;
      });
    },
    [],
  );

  const loadUsers = useCallback(async () => {
    const socket = socketRef.current;
    if (!socket) return;
    try {
      const response = await socket.request<UsersResponse>({ type: 'get_users' });
      setUsers(response.users);
      namesRef.current = new Map(response.users.map((user) => [user.user_id, user.username]));
    } catch {
      /* a failed refresh is not worth interrupting the user */
    }
  }, []);

  const loadGroups = useCallback(async () => {
    const socket = socketRef.current;
    if (!socket) return;
    try {
      const response = await socket.request<GroupsResponse>({ type: 'get_groups' });
      setGroups(response.groups);
    } catch {
      /* optional */
    }
  }, []);

  const loadHistory = useCallback(async (chatId: string) => {
    const socket = socketRef.current;
    const me = sessionRef.current;
    if (!socket || !me) return;

    try {
      const isGroup = chatId.startsWith('grp-');
      const targetId = Number.parseInt(chatId.split('-')[1] ?? '', 10);
      if (Number.isNaN(targetId)) return;

      const response = await socket.request<HistoryResponse>(
        isGroup
          ? { type: 'message_history', group_id: targetId, limit: 100 }
          : { type: 'message_history', with_user_id: targetId, limit: 100 },
      );

      const history: ChatMessage[] = response.messages.map((entry) => ({
        id: `srv-${entry.message_id}`,
        serverId: entry.message_id,
        chatId,
        senderId: entry.sender_id,
        senderName:
          entry.sender_id === me.userId
            ? 'You'
            : namesRef.current.get(entry.sender_id) ?? entry.sender,
        body: entry.message,
        at: entry.timestamp,
        status:
          entry.status === 'read' ? 'read' : entry.status === 'delivered' ? 'delivered' : 'sent',
        mine: entry.sender_id === me.userId,
      }));

      setMessages((prev) => ({ ...prev, [chatId]: history }));
    } catch {
      /* history is best-effort */
    }
  }, []);

  /* ── socket lifecycle ─────────────────────────────────────────────────── */

  useEffect(() => {
    const socket = new ChatSocket({ url: SERVER_URL });
    socketRef.current = socket;

    const offState = socket.onStateChange(setStatus);

    const offEvents = socket.on('*', (frame) => {
      const me = sessionRef.current;

      switch (frame.type) {
        case 'incoming_message': {
          const event = frame as IncomingMessageEvent;
          if (!me) return;
          const chatId = dmChatId(event.sender_id);
          const message: ChatMessage = {
            id: `srv-${event.message_id}`,
            serverId: event.message_id,
            chatId,
            senderId: event.sender_id,
            senderName: namesRef.current.get(event.sender_id) ?? event.sender,
            body: event.message,
            at: event.timestamp,
            status: 'delivered',
            mine: false,
          };
          appendMessage(message);

          if (activeChatRef.current !== chatId) {
            setUnread((prev) => ({ ...prev, [chatId]: (prev[chatId] ?? 0) + 1 }));
            notify(`New message from ${message.senderName}`, message.body);
          }
          break;
        }

        case 'incoming_group_message': {
          const event = frame as IncomingGroupMessageEvent;
          if (!me) return;
          const chatId = groupChatId(event.group_id);
          const message: ChatMessage = {
            id: `srv-${event.message_id}`,
            serverId: event.message_id,
            chatId,
            senderId: event.sender_id,
            senderName: namesRef.current.get(event.sender_id) ?? event.sender,
            body: event.message,
            at: event.timestamp,
            status: 'delivered',
            mine: event.sender_id === me.userId,
          };
          appendMessage(message);
          if (activeChatRef.current !== chatId) {
            setUnread((prev) => ({ ...prev, [chatId]: (prev[chatId] ?? 0) + 1 }));
          }
          break;
        }

        case 'presence': {
          const event = frame as PresenceEvent;
          const online = new Set(event.online.map((entry) => entry.user_id));
          setUsers((prev) =>
            prev.map((user) => ({
              ...user,
              status: online.has(user.user_id) ? 'online' : 'offline',
            })),
          );
          break;
        }

        case 'typing': {
          const event = frame as TypingEvent;
          const chatId = dmChatId(event.sender_id);
          setTyping((prev) => ({ ...prev, [chatId]: event.is_typing }));
          if (event.is_typing) {
            window.setTimeout(() => {
              setTyping((prev) => ({ ...prev, [chatId]: false }));
            }, 4000);
          }
          break;
        }

        case 'delivery_ack':
        case 'read_receipt': {
          const receipt = frame as unknown as { type: string; message_id: number };
          const nextStatus: MessageStatus =
            receipt.type === 'read_receipt' ? 'read' : 'delivered';
          setMessages((prev) => {
            let changed = false;
            const next: Record<string, ChatMessage[]> = {};
            for (const [chatId, thread] of Object.entries(prev)) {
              next[chatId] = thread.map((message) => {
                if (message.serverId !== receipt.message_id) return message;
                changed = true;
                return { ...message, status: nextStatus };
              });
            }
            return changed ? next : prev;
          });
          break;
        }

        case 'server_shutdown':
          notify('Server is shutting down', 'Reconnecting automatically', 'error');
          break;

        case 'error': {
          const error = frame as { code: ErrorCode; message: string; request_type?: string };
          if (!error.request_type) {
            notify('Server error', ERROR_TEXT[error.code] ?? error.message, 'error');
          }
          if (error.code === 'invalid_token' || error.code === 'not_authenticated') {
            // The session died server-side: drop it rather than pretending.
            sessionRef.current = null;
            setSession(null);
            writeStoredSession(null);
          }
          break;
        }

        default:
          break;
      }
    });

    // Resume a tab-scoped session, otherwise just open the connection.
    const stored = readStoredSession();
    void (async () => {
      try {
        await socket.connect();
        if (stored) {
          try {
            const resumed = await socket.request<ResumeResponse>({
              type: 'resume_session',
              session_token: stored.token,
            });
            if (resumed.success) {
              socket.token = stored.token;
              sessionRef.current = stored;
              setSession(stored);
              void loadUsers();
              void loadGroups();
            } else {
              writeStoredSession(null);
            }
          } catch {
            writeStoredSession(null);
          }
        }
      } catch {
        /* the state listener shows 'closed' */
      }
    })();

    return () => {
      offState();
      offEvents();
      socket.close();
      socketRef.current = null;
    };
  }, [appendMessage, loadGroups, loadUsers, notify]);

  useEffect(() => {
    activeChatRef.current = activeChatId;
  }, [activeChatId]);

  /* ── auth ─────────────────────────────────────────────────────────────── */

  const startSession = useCallback(
    (next: Session) => {
      socketRef.current!.token = next.token;
      sessionRef.current = next;
      setSession(next);
      setAuthError(null);
      writeStoredSession(next);
      void loadUsers();
      void loadGroups();
    },
    [loadGroups, loadUsers],
  );

  const login = useCallback(
    async (username: string, password: string) => {
      const socket = socketRef.current;
      if (!socket) {
        setAuthError({ message: 'Not connected to the server' });
        return;
      }
      setBusy(true);
      setAuthError(null);
      try {
        await socket.connect();
        const response = await socket.request<LoginResponse>({
          type: 'login',
          username,
          password,
        });
        if (!response.success || !response.session_token || response.user_id === undefined) {
          setAuthError({
            code: (response.code ?? 'invalid_credentials') as ErrorCode,
            message: response.message,
            retryAfter: response.retry_after,
          });
          return;
        }
        startSession({
          userId: response.user_id,
          username: response.username ?? username,
          token: response.session_token,
          expiresAt: response.expires_at,
        });
      } catch (error) {
        setAuthError(toAuthError(error));
      } finally {
        setBusy(false);
      }
    },
    [startSession],
  );

  const register = useCallback(
    async (username: string, password: string) => {
      const socket = socketRef.current;
      if (!socket) {
        setAuthError({ message: 'Not connected to the server' });
        return;
      }
      setBusy(true);
      setAuthError(null);
      try {
        await socket.connect();
        const created = await socket.request<RegisterResponse>({
          type: 'register',
          username,
          password,
        });
        if (!created.success) {
          setAuthError({ message: created.message, code: 'username_taken' });
          return;
        }
        // Registration does not authenticate: log in straight away so the user
        // is not asked to type the same password twice.
        await login(username, password);
      } catch (error) {
        setAuthError(toAuthError(error));
      } finally {
        setBusy(false);
      }
    },
    [login],
  );

  const logout = useCallback(async () => {
    const socket = socketRef.current;
    if (socket) {
      try {
        await socket.request({ type: 'logout' });
      } catch {
        /* the local teardown below is what matters */
      }
      socket.token = null;
    }
    sessionRef.current = null;
    setSession(null);
    setUsers([]);
    setGroups([]);
    setMessages({});
    setUnread({});
    setTyping({});
    setActiveChatId('');
    writeStoredSession(null);
  }, []);

  /* ── chats ────────────────────────────────────────────────────────────── */

  const openChat = useCallback(
    (chatId: string) => {
      setActiveChatId(chatId);
      setUnread((prev) => ({ ...prev, [chatId]: 0 }));

      if (!messages[chatId]?.length) void loadHistory(chatId);

      // Tell the server we have read the latest incoming message (DM only).
      const socket = socketRef.current;
      const me = sessionRef.current;
      if (!socket || !me || chatId.startsWith('grp-')) return;
      const thread = messages[chatId] ?? [];
      const lastIncoming = [...thread].reverse().find((message) => !message.mine);
      if (lastIncoming?.serverId) {
        socket.send({ type: 'mark_read', message_id: lastIncoming.serverId });
      }
    },
    [loadHistory, messages],
  );

  const sendMessage = useCallback(
    async (chatId: string, body: string) => {
      const socket = socketRef.current;
      const me = sessionRef.current;
      const text = body.trim();
      if (!socket || !me || !text) return;

      const isGroup = chatId.startsWith('grp-');
      const targetId = Number.parseInt(chatId.split('-')[1] ?? '', 10);
      if (Number.isNaN(targetId)) return;

      const tempId = `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      const optimistic: ChatMessage = {
        id: tempId,
        serverId: null,
        chatId,
        senderId: me.userId,
        senderName: 'You',
        body: text,
        at: new Date().toISOString(),
        status: 'sending',
        mine: true,
      };
      appendMessage(optimistic);

      try {
        const response = await socket.request<MessageResponse>(
          isGroup
            ? { type: 'group_message', group_id: targetId, message: text }
            : { type: 'private_message', receiver_id: targetId, message: text },
        );
        patchMessage(
          chatId,
          (message) => message.id === tempId,
          {
            id: `srv-${response.message_id}`,
            serverId: response.message_id,
            status: response.status === 'delivered' ? 'delivered' : 'sent',
          },
        );
      } catch (error) {
        const failure = toAuthError(error);
        patchMessage(chatId, (message) => message.id === tempId, { status: 'failed' });
        notify('Message not sent', failure.message, 'error');
      }
    },
    [appendMessage, notify, patchMessage],
  );

  const notifyTyping = useCallback((chatId: string) => {
    const socket = socketRef.current;
    if (!socket || chatId.startsWith('grp-')) return;
    const peerId = Number.parseInt(chatId.split('-')[1] ?? '', 10);
    if (Number.isNaN(peerId)) return;
    socket.send({ type: 'typing', receiver_id: peerId, is_typing: true });
  }, []);

  const createGroup = useCallback(
    async (name: string, memberIds: number[]) => {
      const socket = socketRef.current;
      if (!socket) return;
      try {
        await socket.request({
          type: 'create_group',
          name,
          members: memberIds,
        });
        await loadGroups();
        notify('Group created', name, 'success');
      } catch (error) {
        notify('Could not create group', toAuthError(error).message, 'error');
      }
    },
    [loadGroups, notify],
  );

  const refreshServerInfo = useCallback(async () => {
    const socket = socketRef.current;
    if (!socket) return;
    try {
      setServerInfo(await socket.request<ServerInfoResponse>({ type: 'server_info' }));
    } catch {
      /* optional */
    }
  }, []);

  /* ── derived ──────────────────────────────────────────────────────────── */

  const chats: Chat[] = useMemo(() => {
    const direct: Chat[] = users
      .filter((user) => user.user_id !== session?.userId)
      .map((user) => {
        const id = dmChatId(user.user_id);
        const thread = messages[id] ?? [];
        return {
          id,
          kind: 'dm' as const,
          title: user.username,
          peerId: user.user_id,
          online: user.status === 'online',
          lastSeen: user.last_seen_at,
          members: [],
          lastMessage: thread[thread.length - 1],
          unread: unread[id] ?? 0,
          typing: typing[id] ?? false,
        };
      });

    const groupChats: Chat[] = groups.map((group) => {
      const id = groupChatId(group.group_id);
      const thread = messages[id] ?? [];
      return {
        id,
        kind: 'group' as const,
        title: group.name,
        groupId: group.group_id,
        online: true,
        lastSeen: null,
        members: group.members,
        lastMessage: thread[thread.length - 1],
        unread: unread[id] ?? 0,
        typing: false,
      };
    });

    return [...groupChats, ...direct].sort((a, b) => {
      const aAt = a.lastMessage?.at ?? '';
      const bAt = b.lastMessage?.at ?? '';
      if (aAt !== bAt) return bAt.localeCompare(aAt);
      return a.title.localeCompare(b.title);
    });
  }, [users, groups, messages, unread, typing, session]);

  const activeChat = chats.find((chat) => chat.id === activeChatId) ?? null;
  const activeMessages = messages[activeChatId] ?? [];

  return {
    // connection
    status,
    serverUrl: SERVER_URL,
    serverInfo,
    refreshServerInfo,
    isConnected: status === 'connected' || status === 'ready',
    // auth
    session,
    authError,
    busy,
    login,
    register,
    logout,
    // data
    users,
    chats,
    activeChat,
    activeChatId,
    messages: activeMessages,
    // actions
    openChat,
    sendMessage,
    notifyTyping,
    createGroup,
    refreshUsers: loadUsers,
    // notices
    notices,
    notify,
    dismissNotice,
  };
}

export type ChatApi = ReturnType<typeof useChat>;
