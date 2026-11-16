import React from 'react';
import { Check, CheckCircle2, Clock, Radio, ShieldCheck, Users } from 'lucide-react';
import type { EmergencyAlert } from '../../lib/emergency';
import { ackCounts, formatWhen, typeMeta } from '../../lib/emergency';
import { Avatar } from '../ui/Avatar';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';

interface EmergencyDetailModalProps {
  open: boolean;
  alert: EmergencyAlert | null;
  onClose: () => void;
  onAcknowledge: (alertId: string, recipientId: number) => void;
  onRequestResolve: (alert: EmergencyAlert) => void;
}

export const EmergencyDetailModal: React.FC<EmergencyDetailModalProps> = ({
  open,
  alert,
  onClose,
  onAcknowledge,
  onRequestResolve,
}) => {
  if (!alert) return null;

  const meta = typeMeta(alert.type);
  const { acked, total, pct } = ackCounts(alert);
  const active = alert.status === 'active';

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={alert.title}
      description={formatWhen(alert.createdAt)}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
          {active && (
            <Button variant="secondary" size="sm" onClick={() => onRequestResolve(alert)}>
              <ShieldCheck className="h-3.5 w-3.5" />
              Resolve
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <span className={`nb-tag ${meta.chip}`}>{meta.label}</span>
          <span
            className={`nb-tag ${
              active
                ? 'border-danger/50 bg-danger/10 text-danger'
                : 'border-border text-muted-foreground'
            }`}
          >
            {active ? 'active' : 'resolved'}
          </span>
          {alert.resolvedAt && (
            <span className="ml-auto font-mono text-[10px] text-muted-foreground">
              resolved {formatWhen(alert.resolvedAt)}
            </span>
          )}
        </div>

        <p className="whitespace-pre-wrap rounded-lg border-2 border-border bg-background px-3 py-2 text-xs leading-relaxed">
          {alert.message}
        </p>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <p className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
              <Users className="h-3 w-3" />
              acknowledgements
            </p>
            <p className="font-mono text-[10px] font-bold text-foreground">
              {acked} of {total} · {pct}%
            </p>
          </div>

          <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-elevated">
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-300"
              style={{ width: `${pct}%` }}
            />
          </div>

          <ul className="space-y-1.5">
            {alert.recipients.map((recipient) => {
              const done = recipient.status === 'acknowledged';
              return (
                <li
                  key={recipient.id}
                  className="flex items-center gap-2.5 rounded-lg border-2 border-border px-2.5 py-2"
                >
                  <Avatar name={recipient.name} size="sm" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-bold">{recipient.name}</p>
                    <p className="flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
                      {done ? (
                        <>
                          <CheckCircle2 className="h-3 w-3 text-primary" />
                          acknowledged {recipient.acknowledgedAt}
                        </>
                      ) : (
                        <>
                          <Clock className="h-3 w-3" />
                          pending
                        </>
                      )}
                    </p>
                  </div>

                  {active && !done && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => onAcknowledge(alert.id, recipient.id)}
                      title="Simulate this recipient acknowledging the alert"
                    >
                      <Check className="h-3 w-3" />
                      Ack
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>

          {total === 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              This alert had no recipients — nobody else was online.
            </p>
          )}
        </div>

        {active && (
          <p className="flex items-start gap-1.5 rounded-lg border-2 border-danger/30 bg-danger/5 px-2.5 py-2 text-[11px] leading-relaxed text-muted-foreground">
            <Radio className="mt-0.5 h-3 w-3 shrink-0 text-danger" />
            Broadcasting is simulated in this build: acknowledgements are recorded locally, not
            sent over the network.
          </p>
        )}
      </div>
    </Modal>
  );
};
