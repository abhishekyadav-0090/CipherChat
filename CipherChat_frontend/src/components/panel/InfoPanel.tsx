import React from 'react';
import { motion } from 'framer-motion';
import { Clock, Lock, Radio, Server, ShieldCheck, Users, X } from 'lucide-react';
import type { ChatApi } from '../../hooks/useChat';
import { relativeTime } from '../../lib/format';
import { slideFromRight } from '../../lib/motion';
import { Avatar } from '../ui/Avatar';

interface InfoPanelProps {
  chat: ChatApi;
  onClose: () => void;
}

/** Small label/value row, mono and uppercase like the rest of the metadata. */
const Row: React.FC<{ icon: React.ReactNode; label: string; value: React.ReactNode }> = ({
  icon,
  label,
  value,
}) => (
  <div className="flex items-start gap-2.5 py-2">
    <span className="mt-0.5 text-muted-foreground">{icon}</span>
    <div className="min-w-0">
      <p className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
        {label}
      </p>
      <p className="truncate text-xs font-medium text-foreground">{value}</p>
    </div>
  </div>
);

export const InfoPanel: React.FC<InfoPanelProps> = ({ chat, onClose }) => {
  const active = chat.activeChat;
  if (!active) return null;

  return (
    <motion.aside
      variants={slideFromRight}
      initial="hidden"
      animate="show"
      exit="exit"
      className="hidden w-[300px] shrink-0 flex-col overflow-y-auto border-l-2 border-border bg-surface lg:flex"
    >
      <div className="flex items-center justify-between border-b-2 border-border px-4 py-3">
        <h3 className="text-xs font-extrabold uppercase tracking-[0.1em] text-muted-foreground">
          Details
        </h3>
        <button
          onClick={onClose}
          className="rounded-lg p-1 text-muted-foreground hover:bg-elevated hover:text-foreground"
          aria-label="Close details"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="flex flex-col items-center gap-2 border-b-2 border-border p-5 text-center">
        {active.kind === 'group' ? (
          <div className="flex h-16 w-16 items-center justify-center rounded-xl border-2 border-border bg-elevated">
            <Users className="h-6 w-6 text-accent-soft" />
          </div>
        ) : (
          <Avatar name={active.title} size="xl" online={active.online} showStatus />
        )}
        <p className="text-sm font-extrabold">{active.title}</p>
        <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
          {active.kind === 'group' ? 'group' : active.online ? 'online' : 'offline'}
        </p>
      </div>

      <div className="divide-y-2 divide-border px-4 py-2">
        {active.kind === 'dm' ? (
          <>
            <Row
              icon={<Clock className="h-3.5 w-3.5" />}
              label="Last seen"
              value={active.online ? 'now' : relativeTime(active.lastSeen)}
            />
            <Row
              icon={<Server className="h-3.5 w-3.5" />}
              label="Route"
              value="via server · TLS"
            />
            <Row
              icon={<Lock className="h-3.5 w-3.5" />}
              label="Transport"
              value={chat.serverUrl.replace('wss://', '')}
            />
          </>
        ) : (
          <>
            <Row
              icon={<Users className="h-3.5 w-3.5" />}
              label="Members"
              value={`${active.members.length}`}
            />
            <div className="py-2">
              <p className="mb-1.5 font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
                Participants
              </p>
              <ul className="space-y-1">
                {active.members.map((member) => (
                  <li key={member} className="flex items-center gap-2 text-xs">
                    <Avatar name={member} size="sm" />
                    <span className="truncate font-medium">{member}</span>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </div>

      <div className="mt-auto space-y-2 border-t-2 border-border p-4">
        <p className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.1em] text-primary">
          <ShieldCheck className="h-3 w-3" />
          Encrypted in transit
        </p>
        <p className="text-[10px] leading-relaxed text-muted-foreground">
          Messages are stored on the server so offline recipients can receive them. This is
          transport encryption, not end-to-end.
        </p>
        <p className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
          <Radio className="h-3 w-3" />
          {chat.isConnected ? 'link healthy' : 'link down'}
        </p>
      </div>
    </motion.aside>
  );
};
