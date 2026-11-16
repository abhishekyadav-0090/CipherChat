import React from 'react';
import { motion } from 'framer-motion';
import {
  ArrowLeft,
  Check,
  LogOut,
  Palette,
  RefreshCw,
  Server,
  ShieldCheck,
  User,
} from 'lucide-react';
import type { ChatApi } from '../../hooks/useChat';
import { cn, relativeTime } from '../../lib/format';
import { fadeUp, listStagger } from '../../lib/motion';
import { Button } from '../ui/Button';

export type Accent = 'lime' | 'purple' | 'cyan' | 'amber';

const ACCENTS: Array<{ id: Accent; label: string; className: string; swatch: string }> = [
  { id: 'lime', label: 'Neon', className: '', swatch: '#39ff14' },
  { id: 'purple', label: 'Purple', className: 'accent-purple', swatch: '#a855f7' },
  { id: 'cyan', label: 'Cyan', className: 'accent-cyan', swatch: '#22d3ee' },
  { id: 'amber', label: 'Amber', className: 'accent-amber', swatch: '#fbbf24' },
];

interface SettingsViewProps {
  chat: ChatApi;
  accent: Accent;
  onAccentChange: (accent: Accent) => void;
  onBack: () => void;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  chat,
  accent,
  onAccentChange,
  onBack,
}) => (
  <section className="flex h-full flex-1 flex-col overflow-y-auto bg-background">
    <header className="sticky top-0 z-10 flex items-center gap-3 border-b-2 border-border bg-surface px-4 py-3">
      <button
        onClick={onBack}
        className="rounded-lg p-1.5 text-muted-foreground hover:bg-elevated hover:text-foreground"
        aria-label="Back to chat"
      >
        <ArrowLeft className="h-4 w-4" />
      </button>
      <h2 className="text-sm font-extrabold">Settings</h2>
    </header>

    <motion.div
      variants={listStagger}
      initial="hidden"
      animate="show"
      className="mx-auto w-full max-w-2xl space-y-4 p-4 sm:p-6"
    >
      {/* Account */}
      <motion.div variants={fadeUp} className="rounded-xl border-2 border-border bg-surface p-5">
        <p className="mb-4 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          <User className="h-3 w-3" /> Account
        </p>
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-lg font-extrabold">{chat.session?.username}</p>
            <p className="font-mono text-[11px] text-muted-foreground">
              user id {chat.session?.userId} · session expires{' '}
              {chat.session?.expiresAt ? relativeTime(chat.session.expiresAt) : 'in 24h'}
            </p>
          </div>
          <Button variant="danger" size="sm" onClick={() => void chat.logout()}>
            <LogOut className="h-3.5 w-3.5" />
            Sign out
          </Button>
        </div>
      </motion.div>

      {/* Appearance */}
      <motion.div variants={fadeUp} className="rounded-xl border-2 border-border bg-surface p-5">
        <p className="mb-4 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          <Palette className="h-3 w-3" /> Accent
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {ACCENTS.map((option) => (
            <button
              key={option.id}
              onClick={() => onAccentChange(option.id)}
              className={cn(
                'flex items-center gap-2 rounded-lg border-2 px-3 py-2 text-xs font-bold transition-colors',
                accent === option.id
                  ? 'border-primary bg-card text-foreground'
                  : 'border-border text-muted-foreground hover:bg-elevated',
              )}
              aria-pressed={accent === option.id}
            >
              <span
                className="h-3.5 w-3.5 rounded-full border-2 border-black/40"
                style={{ background: option.swatch }}
              />
              {option.label}
              {accent === option.id && <Check className="ml-auto h-3 w-3 text-primary" />}
            </button>
          ))}
        </div>
        <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
          Motion follows your operating system's “reduce motion” setting automatically.
        </p>
      </motion.div>

      {/* Server */}
      <motion.div variants={fadeUp} className="rounded-xl border-2 border-border bg-surface p-5">
        <div className="mb-4 flex items-center justify-between">
          <p className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            <Server className="h-3 w-3" /> Server
          </p>
          <Button variant="ghost" size="sm" onClick={() => void chat.refreshServerInfo()}>
            <RefreshCw className="h-3 w-3" />
            Refresh
          </Button>
        </div>

        <dl className="grid grid-cols-2 gap-3 font-mono text-[11px]">
          <Stat label="Address" value={chat.serverUrl.replace('wss://', '')} />
          <Stat label="Transport" value={chat.serverInfo?.transport ?? 'wss'} />
          <Stat label="TLS" value={chat.serverInfo?.tls ? 'enabled' : 'off'} />
          <Stat label="Version" value={chat.serverInfo?.version ?? '—'} />
          <Stat label="Online users" value={String(chat.serverInfo?.stats.users_online ?? '—')} />
          <Stat label="Connections" value={String(chat.serverInfo?.stats.connections ?? '—')} />
        </dl>
      </motion.div>

      {/* Security */}
      <motion.div variants={fadeUp} className="rounded-xl border-2 border-border bg-surface p-5">
        <p className="mb-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-primary">
          <ShieldCheck className="h-3 w-3" /> Security
        </p>
        <ul className="space-y-2 text-[11px] leading-relaxed text-muted-foreground">
          <li>· Passwords are hashed with bcrypt on the server and never returned.</li>
          <li>· Your session token lives in sessionStorage — it dies with this tab.</li>
          <li>· Message bodies are rendered as text only; no HTML is ever injected.</li>
          <li>· The client refuses to connect if the certificate does not verify.</li>
          <li>· Repeated failed logins are throttled server-side, per account and per IP.</li>
        </ul>
        {chat.serverInfo?.security && (
          <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
            events: {Object.entries(chat.serverInfo.security).map(([k, v]) => `${k}=${v}`).join(' · ') || 'none'}
          </p>
        )}
      </motion.div>
    </motion.div>
  </section>
);

const Stat: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-lg border-2 border-border bg-background px-2.5 py-2">
    <dt className="text-[9px] uppercase tracking-[0.1em] text-muted-foreground">{label}</dt>
    <dd className="mt-0.5 truncate font-bold text-foreground">{value}</dd>
  </div>
);
