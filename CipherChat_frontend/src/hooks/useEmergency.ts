/**
 * useEmergency — state for the SOS feature.
 *
 * Kept out of `useChat` on purpose: an emergency is not a chat message, it has
 * its own lifecycle (active → resolved) and its own persistence. When real
 * broadcasting lands, this hook grows a socket call and nothing else changes.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  acknowledgeRecipient,
  createAlert,
  loadEmergencies,
  resolveAlert,
  saveEmergencies,
  type EmergencyAlert,
  type EmergencyType,
} from '../lib/emergency';

export interface EmergencyContact {
  id: number;
  name: string;
}

export function useEmergency() {
  const [emergencies, setEmergencies] = useState<EmergencyAlert[]>(() => loadEmergencies());

  // Persist on every change, so a refresh mid-incident loses nothing.
  useEffect(() => {
    saveEmergencies(emergencies);
  }, [emergencies]);

  const activeEmergency = useMemo(
    () => emergencies.find((alert) => alert.status === 'active') ?? null,
    [emergencies],
  );

  const history = useMemo(
    () => [...emergencies].sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
    [emergencies],
  );

  const trigger = useCallback(
    (type: EmergencyType, message: string, recipients: EmergencyContact[]): EmergencyAlert => {
      const alert = createAlert(type, message, recipients);
      setEmergencies((prev) => [alert, ...prev]);
      return alert;
    },
    [],
  );

  const acknowledge = useCallback((alertId: string, recipientId: number) => {
    setEmergencies((prev) =>
      prev.map((alert) =>
        alert.id === alertId ? acknowledgeRecipient(alert, recipientId) : alert,
      ),
    );
  }, []);

  const resolve = useCallback((alertId: string) => {
    setEmergencies((prev) =>
      prev.map((alert) => (alert.id === alertId ? resolveAlert(alert) : alert)),
    );
  }, []);

  const clearHistory = useCallback(() => {
    setEmergencies((prev) => prev.filter((alert) => alert.status === 'active'));
  }, []);

  return {
    emergencies,
    history,
    activeEmergency,
    trigger,
    acknowledge,
    resolve,
    clearHistory,
  };
}

export type EmergencyApi = ReturnType<typeof useEmergency>;
