import React, { useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  History,
  Radio,
  ShieldCheck,
  Siren,
  Users,
} from 'lucide-react';
import type { EmergencyAlert, EmergencyType } from '../../lib/emergency';
import {
  EMERGENCY_TEMPLATES,
  EMERGENCY_TYPES,
  ackCounts,
  formatWhen,
  typeMeta,
} from '../../lib/emergency';
import type { EmergencyContact } from '../../hooks/useEmergency';
import { fadeUp, listStagger, springSoft } from '../../lib/motion';
import { cn } from '../../lib/format';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { Avatar } from '../ui/Avatar';
import { SosConfirmModal } from './SosConfirmModal';
import { EmergencyDetailModal } from './EmergencyDetailModal';

interface EmergencyCenterViewProps {
  contacts: EmergencyContact[];
  emergencies: EmergencyAlert[];
  activeEmergency: EmergencyAlert | null;
  onTrigger: (type: EmergencyType, message: string, recipients: EmergencyContact[]) => void;
  onAcknowledge: (alertId: string, recipientId: number) => void;
  onResolve: (alertId: string) => void;
  notify: (title: string, body?: string, tone?: 'info' | 'success' | 'error') => void;
}

const MIN_MESSAGE = 10;
const MAX_MESSAGE = 400;

export const EmergencyCenterView: React.FC<EmergencyCenterViewProps> = ({
  contacts,
  emergencies,
  activeEmergency,
  onTrigger,
  onAcknowledge,
  onResolve,
  notify,
}) => {
  const [type, setType] = useState<EmergencyType>('medical');
  const [message, setMessage] = useState('');
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [resolveTarget, setResolveTarget] = useState<EmergencyAlert | null>(null);
  const [filter, setFilter] = useState<'all' | 'active' | 'resolved'>('all');

  // Live lookup: an acknowledgement made from the detail modal must be visible
  // immediately, so the modal reads the record by id instead of a snapshot.
  const detailAlert = useMemo(
    () => (detailId ? emergencies.find((alert) => alert.id === detailId) ?? null : null),
    [emergencies, detailId],
  );

  const filtered = useMemo(
    () =>
      emergencies.filter((alert) =>
        filter === 'all' ? true : alert.status === filter,
      ),
    [emergencies, filter],
  );

  const meta = typeMeta(type);
  const trimmed = message.trim();
  const messageValid = trimmed.length >= MIN_MESSAGE;
  const canSend = messageValid && !activeEmergency;

  const handleConfirm = () => {
    onTrigger(type, trimmed, contacts);
    setConfirmOpen(false);
    setMessage('');
    notify(
      'Emergency broadcast sent',
      `${meta.label} alert delivered to ${contacts.length} recipient${
        contacts.length === 1 ? '' : 's'
      }`,
      'error',
    );
  };

  const handleResolve = () => {
    if (!resolveTarget) return;
    onResolve(resolveTarget.id);
    setResolveTarget(null);
    notify('Emergency resolved', 'Moved to history. The record is kept.', 'success');
  };

  return (
    <section className="flex h-full min-h-0 flex-1 flex-col overflow-y-auto bg-background">
      {/* Header */}
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b-2 border-danger/40 bg-surface px-4 py-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg border-2 border-danger/50 bg-danger/15">
          <Siren className="h-4 w-4 text-danger" />
        </div>
        <div className="min-w-0">
          <h1 className="text-sm font-extrabold leading-tight">Emergency Center</h1>
          <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
            broadcast to {contacts.length} reachable {contacts.length === 1 ? 'node' : 'nodes'}
          </p>
        </div>
      </header>

      <div className="mx-auto grid w-full max-w-5xl gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        {/* ── Composer ─────────────────────────────────────────────────── */}
        <motion.div variants={listStagger} initial="hidden" animate="show" className="space-y-4">
          <motion.div variants={fadeUp} className="rounded-xl border-2 border-border bg-surface p-4">
            <p className="mb-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
              <AlertTriangle className="h-3 w-3 text-danger" />
              1 · emergency type
            </p>

            <div className="grid grid-cols-2 gap-2">
              {EMERGENCY_TYPES.map((option) => {
                const selected = option.id === type;
                return (
                  <button
                    key={option.id}
                    onClick={() => setType(option.id)}
                    disabled={Boolean(activeEmergency)}
                    className={cn(
                      'flex flex-col items-start gap-0.5 rounded-lg border-2 px-3 py-2 text-left transition-colors disabled:opacity-50',
                      selected
                        ? `${option.chip} border-2`
                        : 'border-border hover:bg-elevated',
                    )}
                    aria-pressed={selected}
                  >
                    <span className="flex items-center gap-1.5 text-xs font-bold">
                      <span className={cn('h-1.5 w-1.5 rounded-full', option.dot)} />
                      {option.label}
                    </span>
                    <span className="text-[10px] leading-tight text-muted-foreground">
                      {option.blurb}
                    </span>
                  </button>
                );
              })}
            </div>
          </motion.div>

          <motion.div variants={fadeUp} className="rounded-xl border-2 border-border bg-surface p-4">
            <p className="mb-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
              <Radio className="h-3 w-3" />
              2 · what is happening
            </p>

            <div className="mb-2 flex flex-wrap gap-1.5">
              {EMERGENCY_TEMPLATES[type].map((template) => (
                <button
                  key={template}
                  onClick={() => setMessage(template)}
                  disabled={Boolean(activeEmergency)}
                  className="rounded-lg border-2 border-border px-2 py-1 text-[10px] font-medium text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground disabled:opacity-50"
                >
                  {template.length > 38 ? `${template.slice(0, 38)}…` : template}
                </button>
              ))}
            </div>

            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value.slice(0, MAX_MESSAGE))}
              disabled={Boolean(activeEmergency)}
              rows={4}
              placeholder="State your situation, your location or nearest landmark, and what help you need."
              aria-label="Emergency message"
              className="w-full resize-none rounded-lg border-2 border-border bg-background px-3 py-2 text-xs leading-relaxed text-foreground placeholder:text-muted-foreground/60 focus:border-danger/60 focus:outline-none disabled:opacity-60"
            />

            <div className="mt-1.5 flex items-center justify-between font-mono text-[10px]">
              <span className={messageValid ? 'text-muted-foreground' : 'text-danger'}>
                {messageValid ? 'ready' : `at least ${MIN_MESSAGE} characters`}
              </span>
              <span className="text-muted-foreground">
                {trimmed.length}/{MAX_MESSAGE}
              </span>
            </div>
          </motion.div>

          <motion.div variants={fadeUp}>
            <Button
              variant="danger"
              size="lg"
              disabled={!canSend}
              onClick={() => setConfirmOpen(true)}
              className="w-full text-sm"
            >
              <Siren className="h-4 w-4" />
              {activeEmergency ? 'An emergency is already active' : `Send SOS to ${contacts.length}`}
            </Button>
            {activeEmergency && (
              <p className="mt-2 text-center text-[11px] leading-relaxed text-muted-foreground">
                Resolve the active incident before starting another one.
              </p>
            )}
          </motion.div>
        </motion.div>

        {/* ── Active + history ─────────────────────────────────────────── */}
        <div className="space-y-4">
          <AnimatePresence mode="wait">
            {activeEmergency && (
              <motion.div
                key={activeEmergency.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={springSoft}
                className="rounded-xl border-2 border-danger/50 bg-danger/5 p-4"
              >
                <div className="mb-2 flex items-center justify-between">
                  <p className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-danger">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-danger" />
                    active
                  </p>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {formatWhen(activeEmergency.createdAt)}
                  </span>
                </div>

                <p className="text-xs font-extrabold">{activeEmergency.title}</p>
                <p className="mt-1 line-clamp-3 text-[11px] leading-relaxed text-muted-foreground">
                  {activeEmergency.message}
                </p>

                {(() => {
                  const { acked, total, pct } = ackCounts(activeEmergency);
                  return (
                    <div className="mt-3">
                      <div className="mb-1 flex items-center justify-between font-mono text-[10px]">
                        <span className="text-muted-foreground">
                          {acked} of {total} acknowledged
                        </span>
                        <span className="font-bold text-foreground">{pct}%</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-elevated">
                        <motion.div
                          className="h-full rounded-full bg-danger"
                          initial={{ width: 0 }}
                          animate={{ width: `${pct}%` }}
                          transition={springSoft}
                        />
                      </div>
                    </div>
                  );
                })()}

                <div className="mt-3 flex gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    className="flex-1"
                    onClick={() => setDetailId(activeEmergency.id)}
                  >
                    <Users className="h-3 w-3" />
                    Recipients
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    className="flex-1"
                    onClick={() => setResolveTarget(activeEmergency)}
                  >
                    <ShieldCheck className="h-3 w-3" />
                    Resolve
                  </Button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="rounded-xl border-2 border-border bg-surface p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                <History className="h-3 w-3" />
                history
              </p>
              <span className="font-mono text-[10px] text-muted-foreground">{filtered.length}</span>
            </div>

            <div className="mb-3 flex gap-1">
              {(['all', 'active', 'resolved'] as const).map((option) => (
                <button
                  key={option}
                  onClick={() => setFilter(option)}
                  className={cn(
                    'rounded-lg border-2 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.08em] transition-colors',
                    filter === option
                      ? 'border-primary/50 bg-card text-primary'
                      : 'border-border text-muted-foreground hover:bg-elevated',
                  )}
                >
                  {option}
                </button>
              ))}
            </div>

            {filtered.length === 0 ? (
              <p className="py-6 text-center text-[11px] leading-relaxed text-muted-foreground">
                No emergencies recorded yet.
                <br />
                Records are kept in this browser.
              </p>
            ) : (
              <ul className="max-h-[320px] space-y-1.5 overflow-y-auto">
                {filtered.map((alert) => {
                  const meta = typeMeta(alert.type);
                  const { acked, total } = ackCounts(alert);
                  const isActive = alert.status === 'active';
                  return (
                    <li key={alert.id}>
                      <button
                        onClick={() => setDetailId(alert.id)}
                        className="group flex w-full items-start gap-2.5 rounded-lg border-2 border-border px-2.5 py-2 text-left transition-colors hover:border-border-strong hover:bg-elevated"
                      >
                        <span
                          className={cn(
                            'mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border-2',
                            isActive
                              ? 'border-danger/50 bg-danger/10 text-danger'
                              : 'border-border bg-elevated text-muted-foreground',
                          )}
                        >
                          {isActive ? (
                            <Siren className="h-3 w-3" />
                          ) : (
                            <CheckCircle2 className="h-3 w-3" />
                          )}
                        </span>

                        <span className="min-w-0 flex-1">
                          <span className="flex items-baseline justify-between gap-2">
                            <span className="truncate text-xs font-bold">{meta.label}</span>
                            <span className="shrink-0 font-mono text-[9px] uppercase text-muted-foreground">
                              {isActive ? 'active' : 'resolved'}
                            </span>
                          </span>
                          <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
                            {formatWhen(alert.createdAt)} · {acked}/{total} acked
                          </span>
                        </span>

                        <ChevronRight className="mt-1 h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <p className="flex items-start gap-1.5 px-1 text-[10px] leading-relaxed text-muted-foreground">
            <Avatar name="i" size="sm" className="hidden" />
            Broadcast and acknowledgements are simulated in this build. Records persist in this
            browser only.
          </p>
        </div>
      </div>

      {/* ── Modals ───────────────────────────────────────────────────── */}
      <SosConfirmModal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={handleConfirm}
        type={type}
        message={message}
        recipients={contacts}
      />

      <EmergencyDetailModal
        open={Boolean(detailAlert)}
        alert={detailAlert}
        onClose={() => setDetailId(null)}
        onAcknowledge={onAcknowledge}
        onRequestResolve={(alert) => {
          setDetailId(null);
          setResolveTarget(alert);
        }}
      />

      <Modal
        open={Boolean(resolveTarget)}
        onClose={() => setResolveTarget(null)}
        title="Resolve this emergency?"
        description="The incident closes and moves to history. This cannot be undone."
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setResolveTarget(null)}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleResolve}>
              <ShieldCheck className="h-3.5 w-3.5" />
              Resolve
            </Button>
          </>
        }
      >
        <p className="text-xs leading-relaxed text-muted-foreground">
          {resolveTarget
            ? `${typeMeta(resolveTarget.type).label} emergency · ${ackCounts(resolveTarget).acked} of ${
                resolveTarget.recipients.length
              } recipients acknowledged. It stays in history with its acknowledgement record.`
            : ''}
        </p>
      </Modal>
    </section>
  );
};
