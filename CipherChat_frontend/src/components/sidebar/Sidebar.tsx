import React, { useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Check,
  LogOut,
  MessageSquarePlus,
  Search,
  ShieldCheck,
  Users,
  X,
} from 'lucide-react';
import type { Chat, ChatApi } from '../../hooks/useChat';
import { clockTime, cn, truncate } from '../../lib/format';
import { listStagger, springSoft } from '../../lib/motion';
import { Avatar } from '../ui/Avatar';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { Input } from '../ui/Input';

interface SidebarProps {
  chat: ChatApi;
  onClose?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ chat, onClose }) => {
  const [query, setQuery] = useState('');
  const [dialog, setDialog] = useState<'dm' | 'group' | null>(null);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return chat.chats;
    return chat.chats.filter((item) => item.title.toLowerCase().includes(needle));
  }, [chat.chats, query]);

  const me = chat.session?.username ?? '';

  return (
    <aside className="flex h-full w-full flex-col border-r-2 border-border bg-surface md:w-[320px] md:shrink-0">
      {/* Brand + account */}
      <div className="flex items-center justify-between gap-2 border-b-2 border-border px-4 py-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border-2 border-primary bg-primary text-primary-foreground">
            <ShieldCheck className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-extrabold leading-tight">CipherChat</p>
            <p className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
              <span
                className={cn(
                  'inline-block h-1.5 w-1.5 rounded-full',
                  chat.isConnected ? 'bg-online animate-nb-pulse' : 'bg-muted-foreground',
                )}
              />
              {me}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {onClose && (
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-muted-foreground hover:bg-elevated hover:text-foreground md:hidden"
              aria-label="Close sidebar"
            >
              <X className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={() => void chat.logout()}
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-elevated hover:text-danger"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="border-b-2 border-border p-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search conversations"
            aria-label="Search conversations"
            className="h-9 w-full rounded-lg border-2 border-border bg-background pl-9 pr-3 text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none"
          />
        </div>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="p-6 text-center">
            <Users className="mx-auto h-6 w-6 text-muted-foreground/50" />
            <p className="mt-2 text-xs font-medium text-muted-foreground">
              {query ? 'No conversations match that search' : 'No one else is registered yet'}
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground/70">
              Register a second account in another tab, or run
              <span className="font-mono"> tools/cli_client.py</span> on the server.
            </p>
          </div>
        ) : (
          <motion.ul variants={listStagger} initial="hidden" animate="show" className="p-2">
            <AnimatePresence initial={false}>
              {filtered.map((item) => (
                <motion.li
                  key={item.id}
                  layout
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={springSoft}
                >
                  <ChatRow
                    item={item}
                    active={item.id === chat.activeChatId}
                    onSelect={() => {
                      chat.openChat(item.id);
                      onClose?.();
                    }}
                  />
                </motion.li>
              ))}
            </AnimatePresence>
          </motion.ul>
        )}
      </div>

      {/* Actions */}
      <div className="grid grid-cols-2 gap-2 border-t-2 border-border p-3">
        <Button variant="secondary" size="sm" onClick={() => setDialog('dm')} className="w-full">
          <MessageSquarePlus className="h-3.5 w-3.5" />
          New chat
        </Button>
        <Button variant="secondary" size="sm" onClick={() => setDialog('group')} className="w-full">
          <Users className="h-3.5 w-3.5" />
          New group
        </Button>
      </div>

      <NewChatDialog open={dialog === 'dm'} onClose={() => setDialog(null)} chat={chat} />
      <NewGroupDialog open={dialog === 'group'} onClose={() => setDialog(null)} chat={chat} />
    </aside>
  );
};

/* ── one row ────────────────────────────────────────────────────────────── */

const ChatRow: React.FC<{ item: Chat; active: boolean; onSelect: () => void }> = ({
  item,
  active,
  onSelect,
}) => (
  <button
    onClick={onSelect}
    className={cn(
      'relative flex w-full items-center gap-3 rounded-lg border-2 px-3 py-2.5 text-left transition-colors',
      active
        ? 'border-primary/60 bg-card'
        : 'border-transparent hover:border-border hover:bg-elevated',
    )}
    aria-current={active ? 'true' : undefined}
  >
    {item.kind === 'group' ? (
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border-2 border-border bg-elevated">
        <Users className="h-4 w-4 text-accent-soft" />
      </div>
    ) : (
      <Avatar name={item.title} size="md" online={item.online} showStatus />
    )}

    <div className="min-w-0 flex-1">
      <div className="flex items-baseline justify-between gap-2">
        <p className={cn('truncate text-sm font-bold', active ? 'text-primary' : 'text-foreground')}>
          {item.title}
        </p>
        {item.lastMessage && (
          <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
            {clockTime(item.lastMessage.at)}
          </span>
        )}
      </div>

      <div className="mt-0.5 flex items-center gap-1.5">
        {item.typing ? (
          <span className="flex items-center gap-1 text-[11px] font-medium text-primary">
            typing
            <span className="flex gap-0.5">
              {[0, 1, 2].map((dot) => (
                <span
                  key={dot}
                  className="h-1 w-1 rounded-full bg-primary animate-typing-dot"
                  style={{ animationDelay: `${dot * 0.15}s` }}
                />
              ))}
            </span>
          </span>
        ) : (
          <p className="truncate text-[11px] text-muted-foreground">
            {item.lastMessage
              ? `${item.lastMessage.mine ? 'You: ' : item.kind === 'group' ? `${item.lastMessage.senderName}: ` : ''}${truncate(item.lastMessage.body, 34)}`
              : item.kind === 'group'
                ? `${item.members.length} members`
                : item.online
                  ? 'online'
                  : 'offline'}
          </p>
        )}
        {item.unread > 0 && (
          <motion.span
            initial={{ scale: 0.6, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="ml-auto flex h-4 min-w-4 items-center justify-center rounded-full border-2 border-primary bg-primary px-1 font-mono text-[9px] font-extrabold text-primary-foreground"
          >
            {item.unread}
          </motion.span>
        )}
      </div>
    </div>
  </button>
);

/* ── dialogs ────────────────────────────────────────────────────────────── */

const NewChatDialog: React.FC<{ open: boolean; onClose: () => void; chat: ChatApi }> = ({
  open,
  onClose,
  chat,
}) => {
  const direct = chat.chats.filter((item) => item.kind === 'dm');

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Start a conversation"
      description="Every registered account on this server is listed here."
    >
      {direct.length === 0 ? (
        <p className="text-xs leading-relaxed text-muted-foreground">
          No other accounts exist yet. Register one in a second browser window.
        </p>
      ) : (
        <ul className="max-h-72 space-y-1.5 overflow-y-auto">
          {direct.map((item) => (
            <li key={item.id}>
              <button
                onClick={() => {
                  chat.openChat(item.id);
                  onClose();
                }}
                className="flex w-full items-center gap-3 rounded-lg border-2 border-border px-3 py-2 text-left transition-colors hover:border-primary/50 hover:bg-elevated"
              >
                <Avatar name={item.title} size="sm" online={item.online} showStatus />
                <span className="text-sm font-bold">{item.title}</span>
                <span className="ml-auto font-mono text-[10px] uppercase text-muted-foreground">
                  {item.online ? 'online' : 'offline'}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
};

const NewGroupDialog: React.FC<{ open: boolean; onClose: () => void; chat: ChatApi }> = ({
  open,
  onClose,
  chat,
}) => {
  const [name, setName] = useState('');
  const [selected, setSelected] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);

  const toggle = (id: number) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) return setError('Give the group a name');
    if (trimmed.length > 48) return setError('Name must be 48 characters or fewer');
    await chat.createGroup(trimmed, selected);
    setName('');
    setSelected([]);
    setError(null);
    onClose();
  };

  const direct = chat.chats.filter((item) => item.kind === 'dm' && item.peerId);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New group"
      description="You are added automatically as the owner."
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={() => void submit()}>
            Create group
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input
          label="Group name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Project team"
          maxLength={48}
          error={error}
        />

        <div>
          <p className="mb-1.5 text-[11px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
            Members
          </p>
          <ul className="max-h-48 space-y-1 overflow-y-auto">
            {direct.map((item) => {
              const checked = selected.includes(item.peerId!);
              return (
                <li key={item.id}>
                  <button
                    onClick={() => toggle(item.peerId!)}
                    className={cn(
                      'flex w-full items-center gap-2.5 rounded-lg border-2 px-2.5 py-1.5 text-left text-xs transition-colors',
                      checked
                        ? 'border-primary/60 bg-primary/10'
                        : 'border-border hover:bg-elevated',
                    )}
                  >
                    <span
                      className={cn(
                        'flex h-4 w-4 items-center justify-center rounded border-2',
                        checked ? 'border-primary bg-primary text-primary-foreground' : 'border-border',
                      )}
                    >
                      {checked && <Check className="h-3 w-3" />}
                    </span>
                    <span className="font-bold">{item.title}</span>
                  </button>
                </li>
              );
            })}
            {direct.length === 0 && (
              <li className="text-xs text-muted-foreground">No other accounts yet.</li>
            )}
          </ul>
        </div>
      </div>
    </Modal>
  );
};
