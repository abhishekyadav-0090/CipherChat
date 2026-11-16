/**
 * Emergency SOS — domain model and persistence.
 *
 * Deliberately separate from the chat protocol: the broadcast is *simulated*.
 * An SOS records who it was sent to and tracks their acknowledgement locally;
 * nothing is sent over the socket yet, so this file has no dependency on
 * `useChat` and can be unit-tested on its own.
 */

export type EmergencyType = 'medical' | 'security' | 'accident' | 'general';
export type EmergencyStatus = 'active' | 'resolved';
export type AckStatus = 'pending' | 'acknowledged';

export interface EmergencyRecipient {
  id: number;
  name: string;
  status: AckStatus;
  acknowledgedAt?: string;
}

export interface EmergencyAlert {
  id: string;
  type: EmergencyType;
  title: string;
  message: string;
  createdAt: string;
  status: EmergencyStatus;
  resolvedAt?: string;
  recipients: EmergencyRecipient[];
}

export interface EmergencyTypeMeta {
  id: EmergencyType;
  label: string;
  blurb: string;
  /** Tailwind classes, so the palette stays in one place. */
  chip: string;
  dot: string;
}

export const EMERGENCY_TYPES: EmergencyTypeMeta[] = [
  {
    id: 'medical',
    label: 'Medical',
    blurb: 'Injury, illness, medication needed',
    chip: 'border-danger/50 bg-danger/10 text-danger',
    dot: 'bg-danger',
  },
  {
    id: 'security',
    label: 'Security',
    blurb: 'Threat, intrusion, unsafe situation',
    chip: 'border-amber-500/50 bg-amber-500/10 text-amber-400',
    dot: 'bg-amber-400',
  },
  {
    id: 'accident',
    label: 'Accident',
    blurb: 'Collision, fire, structural damage',
    chip: 'border-orange-500/50 bg-orange-500/10 text-orange-400',
    dot: 'bg-orange-400',
  },
  {
    id: 'general',
    label: 'General',
    blurb: 'Anything else that needs help now',
    chip: 'border-accent-soft/40 bg-accent-soft/10 text-accent-soft',
    dot: 'bg-accent-soft',
  },
];

export function typeMeta(type: EmergencyType): EmergencyTypeMeta {
  return EMERGENCY_TYPES.find((entry) => entry.id === type) ?? EMERGENCY_TYPES[3];
}

/** Suggested messages — one tap fills the composer, which matters in a panic. */
export const EMERGENCY_TEMPLATES: Record<EmergencyType, string[]> = {
  medical: [
    'Medical emergency — someone needs help urgently at my location.',
    'I need medication / an ambulance. Please respond as soon as you see this.',
  ],
  security: [
    'Security concern — I do not feel safe here. Please check on me.',
    'Unwanted person near my location. Please respond.',
  ],
  accident: [
    'Accident at my location. Injuries possible. Please come.',
    'Fire / structural damage here. Keeping clear. Please respond.',
  ],
  general: [
    'I need help now. Please acknowledge this alert.',
    'Emergency at my location. Please respond as soon as you can.',
  ],
};

const STORAGE_KEY = 'cipherchat.emergencies.v1';
const MAX_RECORDS = 50;

/** localStorage read, tolerant of anything that is not a valid array. */
export function loadEmergencies(): EmergencyAlert[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item): item is EmergencyAlert =>
        Boolean(item) &&
        typeof item.id === 'string' &&
        typeof item.message === 'string' &&
        Array.isArray(item.recipients),
    );
  } catch {
    return [];
  }
}

export function saveEmergencies(emergencies: EmergencyAlert[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(emergencies.slice(0, MAX_RECORDS)));
  } catch {
    /* private mode or quota — the session still works, it just will not persist */
  }
}

export function createAlert(
  type: EmergencyType,
  message: string,
  recipients: Array<{ id: number; name: string }>,
): EmergencyAlert {
  const now = new Date();
  return {
    id: `sos-${now.getTime()}`,
    type,
    title: `${typeMeta(type).label} emergency`,
    message: message.trim(),
    createdAt: now.toISOString(),
    status: 'active',
    recipients: recipients.map((recipient) => ({
      id: recipient.id,
      name: recipient.name,
      status: 'pending',
    })),
  };
}

export function acknowledgeRecipient(
  alert: EmergencyAlert,
  recipientId: number,
): EmergencyAlert {
  if (alert.status !== 'active') return alert;
  return {
    ...alert,
    recipients: alert.recipients.map((recipient) =>
      recipient.id === recipientId && recipient.status === 'pending'
        ? {
            ...recipient,
            status: 'acknowledged',
            acknowledgedAt: new Date().toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            }),
          }
        : recipient,
    ),
  };
}

export function resolveAlert(alert: EmergencyAlert): EmergencyAlert {
  if (alert.status === 'resolved') return alert;
  return { ...alert, status: 'resolved', resolvedAt: new Date().toISOString() };
}

export function ackCounts(alert: EmergencyAlert): { acked: number; total: number; pct: number } {
  const total = alert.recipients.length;
  const acked = alert.recipients.filter((r) => r.status === 'acknowledged').length;
  return { acked, total, pct: total === 0 ? 0 : Math.round((acked / total) * 100) };
}

export function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return `${date.toLocaleDateString([], { day: 'numeric', month: 'short' })} · ${date.toLocaleTimeString(
    [],
    { hour: '2-digit', minute: '2-digit' },
  )}`;
}
