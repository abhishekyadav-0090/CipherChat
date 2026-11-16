import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowDown } from 'lucide-react';
import type { Chat, ChatMessage } from '../../hooks/useChat';
import { dayLabel } from '../../lib/format';
import { MessageBubble } from './MessageBubble';

interface MessageListProps {
  chat: Chat;
  messages: ChatMessage[];
}

export const MessageList: React.FC<MessageListProps> = ({ chat, messages }) => {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);

  // Auto-scroll only when the user is already at the bottom — otherwise reading
  // history would yank them away from where they are.
  useEffect(() => {
    if (!pinned) return;
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, pinned, chat.id]);

  useEffect(() => {
    setPinned(true);
  }, [chat.id]);

  const onScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    setPinned(distance < 80);
  };

  const grouped = useMemo(() => {
    const out: Array<{ day: string; items: ChatMessage[] }> = [];
    for (const message of messages) {
      const day = dayLabel(message.at);
      const last = out[out.length - 1];
      if (last && last.day === day) last.items.push(message);
      else out.push({ day, items: [message] });
    }
    return out;
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: 'spring', stiffness: 300, damping: 26 }}
          className="flex h-14 w-14 items-center justify-center rounded-xl border-2 border-border bg-surface"
        >
          <span className="font-mono text-lg font-extrabold text-primary">
            {chat.kind === 'group' ? '#' : '@'}
          </span>
        </motion.div>
        <div>
          <p className="text-sm font-bold">
            {chat.kind === 'group' ? `Start the ${chat.title} group` : `Say hello to ${chat.title}`}
          </p>
          <p className="mt-1 max-w-xs text-xs leading-relaxed text-muted-foreground">
            Messages are stored on the server. If {chat.kind === 'group' ? 'a member is' : 'they are'}{' '}
            offline, the message is delivered when they next sign in.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex-1 overflow-hidden">
      <div
        ref={containerRef}
        onScroll={onScroll}
        className="h-full overflow-y-auto px-4 py-4"
        role="log"
        aria-live="polite"
      >
        {grouped.map((group) => (
          <div key={group.day}>
            <div className="my-4 flex items-center gap-3">
              <span className="h-px flex-1 bg-border" />
              <span className="nb-tag text-muted-foreground">{group.day}</span>
              <span className="h-px flex-1 bg-border" />
            </div>

            <div className="space-y-1">
              {group.items.map((message, index) => {
                const next = group.items[index + 1];
                const sameAuthor = next?.senderId === message.senderId;
                const previous = group.items[index - 1];
                const newRun = previous?.senderId !== message.senderId;
                return (
                  <MessageBubble
                    key={message.id}
                    message={message}
                    showAuthor={newRun && !message.mine}
                    showTail={!sameAuthor}
                  />
                );
              })}
            </div>
          </div>
        ))}
        <div ref={bottomRef} className="h-2" />
      </div>

      <AnimatePresence>
        {!pinned && (
          <motion.button
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            onClick={() => {
              setPinned(true);
              bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
            }}
            className="absolute bottom-4 right-4 flex h-9 w-9 items-center justify-center rounded-full border-2 border-border bg-surface nb-shadow-sm hover:border-primary/60"
            aria-label="Jump to latest messages"
          >
            <ArrowDown className="h-4 w-4" />
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
};
