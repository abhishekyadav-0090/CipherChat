/**
 * Wire protocol for the CipherChat backend.
 *
 * This file is the TypeScript mirror of `backend/docs/PROTOCOL.md`. If the two
 * ever disagree, the document is right and this file is the bug.
 *
 * Transport: one JSON object per WebSocket frame (wss://host:5443). No length
 * prefix — WebSocket already gives us message boundaries. The TCP transport
 * uses a 4-byte big-endian length prefix instead; this client only speaks WSS.
 */

export const MAX_MESSAGE_CHARS = 4000;
export const MAX_FRAME_BYTES = 65536;

/* ── errors ──────────────────────────────────────────────────────────────── */

export type ErrorCode =
  | 'not_authenticated'
  | 'invalid_credentials'
  | 'username_taken'
  | 'username_reserved'
  | 'bad_username'
  | 'weak_password'
  | 'bad_password'
  | 'throttled'
  | 'unknown_recipient'
  | 'unknown_group'
  | 'not_a_member'
  | 'self_message'
  | 'empty_message'
  | 'message_too_long'
  | 'bad_message'
  | 'impersonation_rejected'
  | 'not_your_message'
  | 'invalid_token'
  | 'malformed_json'
  | 'unknown_type'
  | 'frame_too_large'
  | 'frame_error'
  | 'server_full'
  | 'idle_timeout'
  | 'server_error';

export interface ErrorResponse {
  type: 'error';
  code: ErrorCode;
  message: string;
  request_type?: string;
}

/* ── requests ────────────────────────────────────────────────────────────── */

export interface RegisterRequest {
  type: 'register';
  username: string;
  password: string;
}

export interface LoginRequest {
  type: 'login';
  username: string;
  password: string;
}

export interface ResumeSessionRequest {
  type: 'resume_session';
  session_token: string;
}

export interface LogoutRequest {
  type: 'logout';
}

export interface PrivateMessageRequest {
  type: 'private_message';
  receiver_id: number;
  message: string;
}

export interface GroupMessageRequest {
  type: 'group_message';
  group_id: number;
  message: string;
}

export interface GetUsersRequest {
  type: 'get_users';
}

export interface MessageHistoryRequest {
  type: 'message_history';
  with_user_id?: number;
  group_id?: number;
  limit?: number;
  before_id?: number;
}

export interface TypingRequest {
  type: 'typing';
  receiver_id: number;
  is_typing?: boolean;
}

export interface DeliveryAckRequest {
  type: 'delivery_ack';
  message_id: number;
}

export interface MarkReadRequest {
  type: 'mark_read';
  message_id: number;
}

export interface PingRequest {
  type: 'ping';
}

export interface ServerInfoRequest {
  type: 'server_info';
}

export interface CreateGroupRequest {
  type: 'create_group';
  name: string;
  members?: number[];
}

export interface GetGroupsRequest {
  type: 'get_groups';
}

export type ClientRequest =
  | RegisterRequest
  | LoginRequest
  | ResumeSessionRequest
  | LogoutRequest
  | PrivateMessageRequest
  | GroupMessageRequest
  | GetUsersRequest
  | MessageHistoryRequest
  | TypingRequest
  | DeliveryAckRequest
  | MarkReadRequest
  | PingRequest
  | ServerInfoRequest
  | CreateGroupRequest
  | GetGroupsRequest;

/* ── responses ───────────────────────────────────────────────────────────── */

export interface RegisterResponse {
  type: 'register_response';
  success: boolean;
  message: string;
  user_id: number;
  username: string;
}

export interface LoginResponse {
  type: 'login_response';
  success: boolean;
  message: string;
  user_id?: number;
  username?: string;
  session_token?: string;
  expires_at?: string;
  code?: ErrorCode;
  retry_after?: number;
}

export interface ResumeResponse {
  type: 'resume_response';
  success: boolean;
  user_id: number;
  username: string;
  message: string;
}

export interface LogoutResponse {
  type: 'logout_response';
  success: boolean;
  message: string;
}

export interface MessageResponse {
  type: 'message_response';
  success: boolean;
  message_id: number;
  receiver_id?: number;
  receiver?: string;
  group_id?: number;
  status: 'delivered' | 'stored';
  recipients?: number;
}

export interface ProtocolUser {
  user_id: number;
  username: string;
  status: 'online' | 'offline';
  last_seen_at: string | null;
}

export interface UsersResponse {
  type: 'users_response';
  users: ProtocolUser[];
  online_count: number;
}

export interface HistoryMessage {
  message_id: number;
  sender_id: number;
  sender: string;
  receiver_id: number | null;
  group_id: number | null;
  message: string;
  status: 'stored' | 'delivered' | 'read';
  timestamp: string;
}

export interface HistoryResponse {
  type: 'history_response';
  success: boolean;
  with_user_id?: number;
  with_username?: string;
  group_id?: number;
  count: number;
  messages: HistoryMessage[];
}

export interface PongResponse {
  type: 'pong';
  server_time: string;
}

export interface GroupResponse {
  type: 'group_response';
  success: boolean;
  group_id: number;
  name: string;
  members: string[];
}

export interface GroupsResponse {
  type: 'groups_response';
  groups: Array<{ group_id: number; name: string; owner_id: number; members: string[] }>;
}

export interface ServerInfoResponse {
  type: 'server_info_response';
  name: string;
  version: string;
  tls: boolean;
  transport: string;
  max_message_chars: number;
  max_frame_bytes: number;
  stats: {
    connections: number;
    users_online: number;
    max_clients: number;
    total_accepted: number;
    total_rejected: number;
  };
  security: Record<string, number>;
}

/* ── server-initiated events ─────────────────────────────────────────────── */

export interface IncomingMessageEvent {
  type: 'incoming_message';
  message_id: number;
  sender_id: number;
  sender: string;
  receiver_id: number;
  message: string;
  status: string;
  timestamp: string;
  offline_replay?: boolean;
}

export interface IncomingGroupMessageEvent {
  type: 'incoming_group_message';
  message_id: number;
  group_id: number;
  group_name?: string;
  sender_id: number;
  sender: string;
  message: string;
  timestamp: string;
}

export interface PresenceEvent {
  type: 'presence';
  online: Array<{ user_id: number; username: string }>;
  online_count: number;
}

export interface TypingEvent {
  type: 'typing';
  sender_id: number;
  sender: string;
  is_typing: boolean;
}

export interface DeliveryAckEvent {
  type: 'delivery_ack';
  message_id: number;
  receiver_id: number;
  status: string;
}

export interface ReadReceiptEvent {
  type: 'read_receipt';
  message_id: number;
  reader_id: number;
  status: string;
}

export interface ServerShutdownEvent {
  type: 'server_shutdown';
  message: string;
}

/** Every reply the server can send to a request. */
export type ServerResponse =
  | RegisterResponse
  | LoginResponse
  | ResumeResponse
  | LogoutResponse
  | MessageResponse
  | UsersResponse
  | HistoryResponse
  | PongResponse
  | ServerInfoResponse
  | GroupResponse
  | GroupsResponse
  | ErrorResponse;

/** Anything that can arrive on the wire. */
export type ServerFrame = ServerEvent | ServerResponse;

export type ServerEvent =
  | IncomingMessageEvent
  | IncomingGroupMessageEvent
  | PresenceEvent
  | TypingEvent
  | DeliveryAckEvent
  | ReadReceiptEvent
  | ServerShutdownEvent
  | ErrorResponse;

/**
 * Which response type answers which request. Used by the socket client to
 * correlate a request with its reply — the protocol has no request IDs, so the
 * type pair is the correlation key.
 */
export const RESPONSE_FOR: Record<string, string[]> = {
  register: ['register_response'],
  login: ['login_response'],
  resume_session: ['resume_response'],
  logout: ['logout_response'],
  private_message: ['message_response'],
  group_message: ['message_response'],
  get_users: ['users_response'],
  message_history: ['history_response'],
  ping: ['pong'],
  server_info: ['server_info_response'],
  create_group: ['group_response'],
  get_groups: ['groups_response'],
  // Fire-and-forget: these never answer.
  typing: [],
  delivery_ack: [],
  mark_read: [],
};

/** Requests whose reply is worth waiting for. */
export const EXPECTS_REPLY = new Set(Object.keys(RESPONSE_FOR).filter(
  (key) => RESPONSE_FOR[key].length > 0,
));

export const USERNAME_MIN = 3;
export const USERNAME_MAX = 24;
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 128;

export const USERNAME_RE = /^[A-Za-z][A-Za-z0-9_]*$/;

/** Client-side mirror of the server's rules, so the user gets instant feedback. */
export function validateUsername(value: string): string | null {
  const username = value.trim();
  if (username.length < USERNAME_MIN) return `Username must be at least ${USERNAME_MIN} characters`;
  if (username.length > USERNAME_MAX) return `Username must be at most ${USERNAME_MAX} characters`;
  if (!USERNAME_RE.test(username)) {
    return 'Start with a letter; use only letters, digits and underscore';
  }
  return null;
}

export function validatePassword(value: string): string | null {
  if (value.length < PASSWORD_MIN) return `Password must be at least ${PASSWORD_MIN} characters`;
  if (value.length > PASSWORD_MAX) return `Password must be at most ${PASSWORD_MAX} characters`;
  if (value.trim() === '') return 'Password cannot be only spaces';
  return null;
}

/** Human-readable explanation for every error code the server can return. */
export const ERROR_TEXT: Record<ErrorCode, string> = {
  not_authenticated: 'Your session ended. Please log in again.',
  invalid_credentials: 'Invalid username or password.',
  username_taken: 'That username is already taken.',
  username_reserved: 'That username is reserved — pick another.',
  bad_username: 'That username is not valid.',
  weak_password: 'That password is too short.',
  bad_password: 'That password is not valid.',
  throttled: 'Too many failed attempts. Wait a moment and try again.',
  unknown_recipient: 'That user no longer exists.',
  unknown_group: 'That group no longer exists.',
  not_a_member: 'You are not a member of that group.',
  self_message: 'You cannot message yourself.',
  empty_message: 'Message cannot be empty.',
  message_too_long: `Message is longer than ${MAX_MESSAGE_CHARS} characters.`,
  bad_message: 'That message could not be sent.',
  impersonation_rejected: 'Sender identity did not match your session.',
  not_your_message: 'That message is not yours.',
  invalid_token: 'Your session expired. Please log in again.',
  malformed_json: 'Malformed request.',
  unknown_type: 'Unsupported request.',
  frame_too_large: 'Message too large to send.',
  frame_error: 'Connection framing error.',
  server_full: 'The server is full. Try again shortly.',
  idle_timeout: 'Disconnected for inactivity.',
  server_error: 'Server error. Try again.',
};
