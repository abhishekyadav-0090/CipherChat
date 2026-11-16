import React, { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { MessageSquare, Settings, Siren, Users } from 'lucide-react';
import type { ChatApi } from '../../hooks/useChat';
import { springSoft } from '../../lib/motion';
import { cn } from '../../lib/format';
import { Sidebar } from '../sidebar/Sidebar';
import { ChatView } from '../chat/ChatView';
import { InfoPanel } from '../panel/InfoPanel';
import { SettingsView, type Accent } from '../settings/SettingsView';
import { Button } from '../ui/Button';
import { useEmergency } from '../../hooks/useEmergency';
import { EmergencyCenterView } from '../emergency/EmergencyCenterView';
import { EmergencyBanner } from '../emergency/EmergencyBanner';

interface AppShellProps {
  chat: ChatApi;
  accent: Accent;
  onAccentChange: (accent: Accent) => void;
}

export const AppShell: React.FC<AppShellProps> = ({ chat, accent, onAccentChange }) => {
  const [view, setView] = useState<'chat' | 'settings' | 'emergency'>('chat');
  const [panelOpen, setPanelOpen] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const emergency = useEmergency();

  // Everyone we can currently reach becomes a potential recipient.
  const emergencyContacts = React.useMemo(
    () =>
      chat.chats
        .filter((item) => item.kind === 'dm' && typeof item.peerId === 'number')
        .map((item) => ({ id: item.peerId as number, name: item.title })),
    [chat.chats],
  );

  return (
    <div className="flex h-full w-full overflow-hidden bg-background">
      {/* Desktop sidebar */}
      <div className="hidden md:flex">
        <Sidebar chat={chat} />
      </div>

      {/* Mobile drawer */}
      <AnimatePresence>
        {drawerOpen && (
          <motion.div
            className="fixed inset-0 z-40 flex md:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div
              className="absolute inset-0 bg-black/70"
              onClick={() => setDrawerOpen(false)}
              aria-hidden
            />
            <motion.div
              initial={{ x: -320 }}
              animate={{ x: 0 }}
              exit={{ x: -320 }}
              transition={springSoft}
              className="relative z-10 h-full w-[86%] max-w-[320px]"
            >
              <Sidebar chat={chat} onClose={() => setDrawerOpen(false)} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main */}
      <main className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <div className="flex items-center gap-2 border-b-2 border-border bg-surface px-3 py-2 md:hidden">
          <Button variant="ghost" size="sm" onClick={() => setDrawerOpen(true)}>
            <Users className="h-4 w-4" />
            Chats
          </Button>
          <div className="ml-auto flex items-center gap-1">
            <NavButton
              active={view === 'chat'}
              onClick={() => setView('chat')}
              icon={<MessageSquare className="h-4 w-4" />}
              label="Chat"
            />
            <NavButton
              active={view === 'settings'}
              onClick={() => setView('settings')}
              icon={<Settings className="h-4 w-4" />}
              label="Settings"
            />
            <SosNavButton
              active={view === 'emergency'}
              live={Boolean(emergency.activeEmergency)}
              onClick={() => setView('emergency')}
            />
          </div>
        </div>

        {/* Desktop rail */}
        <div className="hidden items-center gap-1 border-b-2 border-border bg-surface px-3 py-2 md:flex">
          <NavButton
            active={view === 'chat'}
            onClick={() => setView('chat')}
            icon={<MessageSquare className="h-4 w-4" />}
            label="Chat"
          />
          <NavButton
            active={view === 'settings'}
            onClick={() => setView('settings')}
            icon={<Settings className="h-4 w-4" />}
            label="Settings"
          />
          <SosNavButton
            active={view === 'emergency'}
            live={Boolean(emergency.activeEmergency)}
            onClick={() => setView('emergency')}
          />
          <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
            {chat.chats.length} conversation{chat.chats.length === 1 ? '' : 's'}
          </span>
        </div>

        {/* Persistent incident strip — visible from any view but the center itself */}
        {emergency.activeEmergency && view !== 'emergency' && (
          <EmergencyBanner
            alert={emergency.activeEmergency}
            onOpen={() => setView('emergency')}
          />
        )}

        <div className="flex min-h-0 flex-1">
          {view === 'emergency' ? (
            <EmergencyCenterView
              contacts={emergencyContacts}
              emergencies={emergency.history}
              activeEmergency={emergency.activeEmergency}
              onTrigger={emergency.trigger}
              onAcknowledge={emergency.acknowledge}
              onResolve={emergency.resolve}
              notify={chat.notify}
            />
          ) : view === 'settings' ? (
            <SettingsView
              chat={chat}
              accent={accent}
              onAccentChange={onAccentChange}
              onBack={() => setView('chat')}
            />
          ) : chat.activeChat ? (
            <>
              <ChatView
                chat={chat}
                panelOpen={panelOpen}
                onTogglePanel={() => setPanelOpen((open) => !open)}
                onBack={() => setDrawerOpen(true)}
              />
              <AnimatePresence>{panelOpen && <InfoPanel chat={chat} onClose={() => setPanelOpen(false)} />}</AnimatePresence>
            </>
          ) : (
            <EmptyState chat={chat} />
          )}
        </div>
      </main>
    </div>
  );
};

const SosNavButton: React.FC<{ active: boolean; live: boolean; onClick: () => void }> = ({
  active,
  live,
  onClick,
}) => (
  <button
    onClick={onClick}
    className={cn(
      'relative flex items-center gap-2 rounded-lg border-2 px-2.5 py-1.5 text-xs font-bold transition-colors',
      active
        ? 'border-danger/60 bg-danger/15 text-danger'
        : 'border-danger/30 text-danger/80 hover:bg-danger/10 hover:text-danger',
    )}
    aria-current={active ? 'page' : undefined}
  >
    <Siren className="h-4 w-4" />
    SOS
    {live && (
      <span className="absolute -right-1 -top-1 flex h-2.5 w-2.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-danger opacity-75" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-danger" />
      </span>
    )}
  </button>
);

const NavButton: React.FC<{
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}> = ({ active, onClick, icon, label }) => (
  <button
    onClick={onClick}
    className={cn(
      'relative flex items-center gap-2 rounded-lg border-2 px-2.5 py-1.5 text-xs font-bold transition-colors',
      active
        ? 'border-primary/50 bg-card text-primary'
        : 'border-transparent text-muted-foreground hover:bg-elevated hover:text-foreground',
    )}
    aria-current={active ? 'page' : undefined}
  >
    {icon}
    {label}
  </button>
);

const EmptyState: React.FC<{ chat: ChatApi }> = ({ chat }) => (
  <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
    <motion.div
      initial={{ opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={springSoft}
      className="flex h-16 w-16 items-center justify-center rounded-xl border-2 border-border bg-surface nb-shadow-sm"
    >
      <MessageSquare className="h-7 w-7 text-primary" />
    </motion.div>
    <div>
      <p className="text-sm font-extrabold">No conversation selected</p>
      <p className="mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">
        Pick someone from the sidebar, or register a second account in another tab to have
        someone to talk to.
      </p>
    </div>
    <Button variant="secondary" size="sm" onClick={() => void chat.refreshUsers()}>
      Refresh users
    </Button>
  </div>
);
