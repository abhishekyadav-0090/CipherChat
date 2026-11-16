import React from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';
import type { Notice } from '../../hooks/useChat';
import { cn } from '../../lib/format';

interface ToastsProps {
  notices: Notice[];
  onDismiss: (id: string) => void;
}

const toneStyles = {
  info: { icon: Info, ring: 'border-border', text: 'text-muted-foreground' },
  success: { icon: CheckCircle2, ring: 'border-primary/50', text: 'text-primary' },
  error: { icon: AlertTriangle, ring: 'border-danger/50', text: 'text-danger' },
} as const;

export const Toasts: React.FC<ToastsProps> = ({ notices, onDismiss }) => (
  <div
    className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2"
    role="status"
    aria-live="polite"
  >
    <AnimatePresence initial={false}>
      {notices.map((notice) => {
        const tone = toneStyles[notice.tone];
        const Icon = tone.icon;
        return (
          <motion.div
            key={notice.id}
            layout
            initial={{ opacity: 0, x: 24, scale: 0.98 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 24, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 400, damping: 32 }}
            className={cn(
              'pointer-events-auto flex items-start gap-3 rounded-xl border-2 bg-surface p-3 nb-shadow-sm',
              tone.ring,
            )}
          >
            <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', tone.text)} aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-bold text-foreground">{notice.title}</p>
              {notice.body && (
                <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
                  {notice.body}
                </p>
              )}
            </div>
            <button
              onClick={() => onDismiss(notice.id)}
              className="text-muted-foreground transition-colors hover:text-foreground"
              aria-label="Dismiss notification"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </motion.div>
        );
      })}
    </AnimatePresence>
  </div>
);
