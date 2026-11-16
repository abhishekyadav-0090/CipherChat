import React from 'react';
import { motion } from 'framer-motion';
import { AlertCircle, Check, CheckCheck, Clock } from 'lucide-react';
import type { ChatMessage } from '../../hooks/useChat';
import { bubbleIn } from '../../lib/motion';
import { clockTime, cn } from '../../lib/format';

interface MessageBubbleProps {
  message: ChatMessage;
  showAuthor: boolean;
  showTail: boolean;
}

const StatusIcon: React.FC<{ status: ChatMessage['status'] }> = ({ status }) => {
  if (status === 'sending') return <Clock className="h-3 w-3" aria-label="Sending" />;
  if (status === 'failed') return <AlertCircle className="h-3 w-3 text-danger" aria-label="Not sent" />;
  if (status === 'sent') return <Check className="h-3 w-3" aria-label="Sent" />;
  if (status === 'delivered') return <CheckCheck className="h-3 w-3" aria-label="Delivered" />;
  return <CheckCheck className="h-3 w-3" aria-label="Read" />;
};

export const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  showAuthor,
  showTail,
}) => (
  <motion.div
    variants={bubbleIn}
    initial="hidden"
    animate="show"
    className={cn('flex w-full', message.mine ? 'justify-end' : 'justify-start')}
  >
    <div className={cn('max-w-[82%] sm:max-w-[68%]', showTail && 'mb-2')}>
      {showAuthor && !message.mine && (
        <p className="mb-1 pl-1 font-mono text-[10px] font-bold uppercase tracking-[0.08em] text-accent-soft/80">
          {message.senderName}
        </p>
      )}

      <div
        className={cn(
          'rounded-xl border-2 px-3.5 py-2 text-[13px] leading-relaxed',
          message.mine
            ? 'rounded-br-sm border-primary bg-primary text-primary-foreground'
            : 'rounded-bl-sm border-border bg-surface text-foreground',
          message.status === 'failed' && 'border-danger/60',
        )}
      >
        {/* Plain text only — React escapes it, and nothing here is ever HTML. */}
        <p className="whitespace-pre-wrap break-words">{message.body}</p>

        <div
          className={cn(
            'mt-1 flex items-center justify-end gap-1 font-mono text-[10px]',
            message.mine ? 'text-primary-foreground/70' : 'text-muted-foreground',
          )}
        >
          <span>{clockTime(message.at)}</span>
          {message.mine && <StatusIcon status={message.status} />}
        </div>
      </div>
    </div>
  </motion.div>
);
