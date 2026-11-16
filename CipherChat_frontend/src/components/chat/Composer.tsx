import React, { useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Send, WifiOff } from 'lucide-react';
import type { ChatApi } from '../../hooks/useChat';
import { MAX_MESSAGE_CHARS } from '../../lib/protocol';
import { cn } from '../../lib/format';

interface ComposerProps {
  chat: ChatApi;
}

export const Composer: React.FC<ComposerProps> = ({ chat }) => {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lastTypingSent = useRef(0);

  const activeId = chat.activeChat?.id ?? '';
  const offline = !chat.isConnected;
  const remaining = MAX_MESSAGE_CHARS - value.length;
  const canSend = value.trim().length > 0 && !offline;

  const resize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`;
  };

  const submit = () => {
    if (!canSend || !activeId) return;
    void chat.sendMessage(activeId, value);
    setValue('');
    requestAnimationFrame(resize);
    textareaRef.current?.focus();
  };

  const onChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    const next = event.target.value.slice(0, MAX_MESSAGE_CHARS);
    setValue(next);
    resize();

    // Typing notices are throttled to one per 2.5 s — the server relays each one
    // to the peer, so a keystroke-per-notice would be spam.
    const now = Date.now();
    if (next.length > 0 && now - lastTypingSent.current > 2500) {
      lastTypingSent.current = now;
      chat.notifyTyping(activeId);
    }
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t-2 border-border bg-surface p-3">
      {offline && (
        <div className="mb-2 flex items-center gap-2 rounded-lg border-2 border-danger/40 bg-danger/10 px-2.5 py-1.5">
          <WifiOff className="h-3.5 w-3.5 text-danger" />
          <p className="text-[11px] font-medium text-danger">
            Disconnected — reconnecting. Messages cannot be sent until the link is back.
          </p>
        </div>
      )}

      <div
        className={cn(
          'flex items-end gap-2 rounded-xl border-2 bg-background p-2 transition-colors',
          offline ? 'border-border opacity-70' : 'border-border focus-within:border-primary',
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={onChange}
          onKeyDown={onKeyDown}
          rows={1}
          maxLength={MAX_MESSAGE_CHARS}
          disabled={offline || !activeId}
          placeholder={offline ? 'Waiting for the connection…' : 'Write a message…'}
          aria-label="Message"
          className="max-h-[132px] flex-1 resize-none bg-transparent px-1.5 py-1.5 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground/60 focus:outline-none disabled:cursor-not-allowed"
        />

        <div className="flex items-center gap-2 pb-0.5">
          {value.length > MAX_MESSAGE_CHARS * 0.8 && (
            <span
              className={cn(
                'font-mono text-[10px]',
                remaining < 100 ? 'text-danger' : 'text-muted-foreground',
              )}
            >
              {remaining}
            </span>
          )}
          <motion.button
            whileTap={{ scale: 0.92 }}
            onClick={submit}
            disabled={!canSend}
            className={cn(
              'nb-press flex h-9 w-9 items-center justify-center rounded-lg border-2',
              canSend
                ? 'border-primary bg-primary text-primary-foreground nb-shadow-sm'
                : 'cursor-not-allowed border-border bg-elevated text-muted-foreground',
            )}
            aria-label="Send message"
          >
            <Send className="h-4 w-4" />
          </motion.button>
        </div>
      </div>

      <p className="mt-1.5 px-1 font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground/60">
        Enter to send · Shift + Enter for a new line
      </p>
    </div>
  );
};
