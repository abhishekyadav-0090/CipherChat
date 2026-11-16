import React from 'react';
import { motion } from 'framer-motion';
import { ArrowLeft, PanelRightClose, PanelRightOpen, Users } from 'lucide-react';
import type { ChatApi } from '../../hooks/useChat';
import { cn, relativeTime } from '../../lib/format';
import { Avatar } from '../ui/Avatar';
import { MessageList } from './MessageList';
import { Composer } from './Composer';

interface ChatViewProps {
  chat: ChatApi;
  panelOpen: boolean;
  onTogglePanel: () => void;
  onBack?: () => void;
}

export const ChatView: React.FC<ChatViewProps> = ({ chat, panelOpen, onTogglePanel, onBack }) => {
  const active = chat.activeChat;
  if (!active) return null;

  const subtitle = active.typing
    ? 'typing…'
    : active.kind === 'group'
      ? `${active.members.length} members`
      : active.online
        ? 'online'
        : `last seen ${relativeTime(active.lastSeen)}`;

  return (
    <section className="flex h-full min-w-0 flex-1 flex-col bg-background">
      {/* Header */}
      <header className="flex items-center gap-3 border-b-2 border-border bg-surface px-4 py-3">
        {onBack && (
          <button
            onClick={onBack}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-elevated hover:text-foreground md:hidden"
            aria-label="Back to conversations"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
        )}

        {active.kind === 'group' ? (
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border-2 border-border bg-elevated">
            <Users className="h-4 w-4 text-accent-soft" />
          </div>
        ) : (
          <Avatar name={active.title} size="md" online={active.online} showStatus />
        )}

        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-extrabold leading-tight">{active.title}</h2>
          <p
            className={cn(
              'flex items-center gap-1.5 text-[11px] font-medium',
              active.typing ? 'text-primary' : 'text-muted-foreground',
            )}
          >
            {active.kind === 'dm' && active.online && !active.typing && (
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-online" />
            )}
            {subtitle}
          </p>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={onTogglePanel}
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-elevated hover:text-foreground"
            aria-label={panelOpen ? 'Hide details' : 'Show details'}
            title={panelOpen ? 'Hide details' : 'Show details'}
          >
            {panelOpen ? (
              <PanelRightClose className="h-4 w-4" />
            ) : (
              <PanelRightOpen className="h-4 w-4" />
            )}
          </button>
        </div>
      </header>

      {/* Messages */}
      <motion.div
        key={active.id}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }}
        className="flex min-h-0 flex-1 flex-col"
      >
        <MessageList chat={active} messages={chat.messages} />

        {active.typing && (
          <div className="flex items-center gap-2 px-4 pb-1 text-[11px] font-medium text-primary">
            <span className="flex gap-1">
              {[0, 1, 2].map((dot) => (
                <span
                  key={dot}
                  className="h-1.5 w-1.5 rounded-full bg-primary animate-typing-dot"
                  style={{ animationDelay: `${dot * 0.15}s` }}
                />
              ))}
            </span>
            {active.title} is typing
          </div>
        )}

        <Composer chat={chat} />
      </motion.div>
    </section>
  );
};
