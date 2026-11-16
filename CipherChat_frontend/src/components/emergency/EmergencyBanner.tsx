import React from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, Siren } from 'lucide-react';
import type { EmergencyAlert } from '../../lib/emergency';
import { ackCounts, typeMeta } from '../../lib/emergency';

interface EmergencyBannerProps {
  alert: EmergencyAlert;
  onOpen: () => void;
}

/**
 * Persistent strip while an incident is active. It sits above the workspace so
 * the state is never more than a glance away, on any screen.
 */
export const EmergencyBanner: React.FC<EmergencyBannerProps> = ({ alert, onOpen }) => {
  const meta = typeMeta(alert.type);
  const { acked, total } = ackCounts(alert);

  return (
    <motion.button
      onClick={onOpen}
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 320, damping: 28 }}
      className="flex w-full shrink-0 items-center gap-3 border-b-2 border-danger/50 bg-danger/10 px-4 py-2 text-left transition-colors hover:bg-danger/15"
      aria-label="Open the active emergency"
    >
      <span className="relative flex h-6 w-6 shrink-0 items-center justify-center">
        <span className="absolute inset-0 rounded-full bg-danger/30 animate-ping" />
        <Siren className="relative h-4 w-4 text-danger" />
      </span>

      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-extrabold text-danger">
          {meta.label} emergency active
        </p>
        <p className="truncate text-[11px] text-muted-foreground">
          {acked} of {total} acknowledged · {alert.message}
        </p>
      </div>

      <span className="hidden shrink-0 items-center gap-1 font-mono text-[10px] uppercase tracking-[0.08em] text-danger sm:flex">
        Open center
        <ArrowRight className="h-3 w-3" />
      </span>
    </motion.button>
  );
};
