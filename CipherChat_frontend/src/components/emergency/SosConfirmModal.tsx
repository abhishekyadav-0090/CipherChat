import React from 'react';
import { AlertTriangle, Radio, Users } from 'lucide-react';
import type { EmergencyType } from '../../lib/emergency';
import { typeMeta } from '../../lib/emergency';
import { Avatar } from '../ui/Avatar';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';

interface SosConfirmModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  type: EmergencyType;
  message: string;
  recipients: Array<{ id: number; name: string }>;
}

/**
 * Deliberately a second step. An SOS cannot be fired by a stray click — the
 * user has to see the type, the exact wording and who will receive it.
 */
export const SosConfirmModal: React.FC<SosConfirmModalProps> = ({
  open,
  onClose,
  onConfirm,
  type,
  message,
  recipients,
}) => {
  const meta = typeMeta(type);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Send emergency broadcast?"
      description="This alerts everyone listed below. It cannot be unsent."
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" size="sm" onClick={onConfirm}>
            <Radio className="h-3.5 w-3.5" />
            Confirm SOS
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className={`flex items-center gap-2 rounded-lg border-2 px-3 py-2 ${meta.chip}`}>
          <AlertTriangle className="h-4 w-4" />
          <span className="text-xs font-bold uppercase tracking-[0.08em]">{meta.label}</span>
        </div>

        <div>
          <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
            Message
          </p>
          <p className="whitespace-pre-wrap rounded-lg border-2 border-border bg-background px-3 py-2 text-xs leading-relaxed text-foreground">
            {message.trim() || <span className="text-muted-foreground">No message written</span>}
          </p>
        </div>

        <div>
          <p className="mb-2 flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
            <Users className="h-3 w-3" />
            {recipients.length} recipient{recipients.length === 1 ? '' : 's'}
          </p>
          {recipients.length === 0 ? (
            <p className="text-xs leading-relaxed text-danger">
              Nobody else is online. The alert will be logged, but no one will receive it.
            </p>
          ) : (
            <ul className="max-h-40 space-y-1 overflow-y-auto">
              {recipients.map((recipient) => (
                <li
                  key={recipient.id}
                  className="flex items-center gap-2 rounded-lg border-2 border-border px-2 py-1.5"
                >
                  <Avatar name={recipient.name} size="sm" />
                  <span className="text-xs font-medium">{recipient.name}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Modal>
  );
};
