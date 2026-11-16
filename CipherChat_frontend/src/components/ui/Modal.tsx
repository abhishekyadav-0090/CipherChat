import React, { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';
import { scaleIn } from '../../lib/motion';
import { cn } from '../../lib/format';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

export const Modal: React.FC<ModalProps> = ({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  className,
}) => {
  // Escape closes; body scroll is locked while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          role="dialog"
          aria-modal="true"
          aria-label={title}
        >
          <div
            className="absolute inset-0 bg-black/75"
            onClick={onClose}
            aria-hidden
          />
          <motion.div
            variants={scaleIn}
            initial="hidden"
            animate="show"
            exit="exit"
            className={cn(
              'relative w-full max-w-md rounded-xl border-2 border-border bg-surface nb-shadow',
              className,
            )}
          >
            <div className="flex items-start justify-between gap-4 border-b-2 border-border p-5">
              <div>
                <h2 className="text-lg font-extrabold text-foreground">{title}</h2>
                {description && (
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {description}
                  </p>
                )}
              </div>
              <button
                onClick={onClose}
                className="rounded-lg border-2 border-border p-1.5 text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground"
                aria-label="Close dialog"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-5">{children}</div>

            {footer && (
              <div className="flex justify-end gap-2 border-t-2 border-border p-4">{footer}</div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
