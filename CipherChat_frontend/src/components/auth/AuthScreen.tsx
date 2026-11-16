import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  ArrowRight,
  Eye,
  EyeOff,
  Fingerprint,
  Lock,
  Radio,
  Server,
  ShieldCheck,
  User,
  UserPlus,
  Wifi,
  WifiOff,
} from 'lucide-react';
import type { ChatApi } from '../../hooks/useChat';
import { validatePassword, validateUsername } from '../../lib/protocol';
import { fadeUp, listStagger, springSoft } from '../../lib/motion';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { cn } from '../../lib/format';

type Mode = 'login' | 'register';

interface AuthScreenProps {
  chat: ChatApi;
}

const PILLARS = [
  {
    icon: ShieldCheck,
    title: 'TLS in transit',
    body: 'Every frame is encrypted and integrity-checked. A modified packet breaks the connection.',
  },
  {
    icon: Fingerprint,
    title: 'bcrypt at rest',
    body: 'Passwords are hashed server-side and never travel back to this browser.',
  },
  {
    icon: Radio,
    title: 'Delivery you can trust',
    body: 'Offline recipients queue on the server and receive the message on their next login.',
  },
];

export const AuthScreen: React.FC<AuthScreenProps> = ({ chat }) => {
  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [cooldownUntil, setCooldownUntil] = useState(0);
  const [, forceTick] = useState(0);
  const usernameRef = useRef<HTMLInputElement>(null);

  // Count the throttling window down. The value is derived, never synced by an
  // effect; the interval only forces a re-render.
  useEffect(() => {
    if (cooldownUntil <= Date.now()) return;
    const timer = window.setInterval(() => forceTick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [cooldownUntil]);

  useEffect(() => {
    usernameRef.current?.focus();
  }, [mode]);

  const cooldown = Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000));
  const connected = chat.isConnected;
  const disabled = chat.busy || cooldown > 0;

  const switchMode = (next: Mode) => {
    setMode(next);
    setFieldError(null);
    setConfirm('');
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (disabled) return;
    setFieldError(null);

    const usernameProblem = validateUsername(username);
    if (usernameProblem) return setFieldError(usernameProblem);

    const passwordProblem = validatePassword(password);
    if (passwordProblem) return setFieldError(passwordProblem);

    if (mode === 'register' && password !== confirm) {
      return setFieldError('Passwords do not match');
    }

    if (mode === 'register') await chat.register(username.trim(), password);
    else await chat.login(username.trim(), password);

    if (chat.authError) {
      if (chat.authError.retryAfter) {
        setCooldownUntil(Date.now() + chat.authError.retryAfter * 1000);
      }
      return;
    }
    setPassword('');
    setConfirm('');
  };

  const message = fieldError ?? chat.authError?.message ?? null;

  return (
    <div className="relative flex h-full w-full overflow-hidden bg-background">
      {/* Background: engineering grid + one soft accent bloom. Nothing else. */}
      <div className="absolute inset-0 nb-grid opacity-60" aria-hidden />
      <div
        className="pointer-events-none absolute -left-40 top-1/3 h-[420px] w-[420px] rounded-full opacity-20 blur-[120px]"
        style={{ background: 'var(--accent)' }}
        aria-hidden
      />

      {/* ── Brand panel (desktop only) ─────────────────────────────────── */}
      <motion.aside
        initial={{ opacity: 0, x: -16 }}
        animate={{ opacity: 1, x: 0 }}
        transition={springSoft}
        className="relative z-10 hidden w-[46%] max-w-[560px] flex-col justify-between border-r-2 border-border p-10 lg:flex"
      >
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border-2 border-primary bg-primary text-primary-foreground nb-shadow-sm">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xl font-extrabold tracking-tight">CipherChat</p>
              <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                Encrypted · Local-first
              </p>
            </div>
          </div>

          <h1 className="mt-12 text-balance text-4xl font-extrabold leading-[1.05]">
            Messages that
            <br />
            <span className="text-primary">never leave</span> your network.
          </h1>
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-muted-foreground">
            A real client–server chat built on raw TLS sockets. No third-party cloud,
            no analytics, no message leaving the machine you run.
          </p>
        </div>

        <motion.ul
          variants={listStagger}
          initial="hidden"
          animate="show"
          className="mt-10 space-y-4"
        >
          {PILLARS.map((pillar) => (
            <motion.li key={pillar.title} variants={fadeUp} className="flex gap-3">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border-2 border-border bg-surface">
                <pillar.icon className="h-4 w-4 text-primary" />
              </div>
              <div>
                <p className="text-sm font-bold">{pillar.title}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                  {pillar.body}
                </p>
              </div>
            </motion.li>
          ))}
        </motion.ul>

        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground/70">
          Server · {chat.serverUrl}
        </p>
      </motion.aside>

      {/* ── Form panel ─────────────────────────────────────────────────── */}
      <div className="relative z-10 flex flex-1 items-center justify-center p-4 sm:p-8">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...springSoft, delay: 0.06 }}
          className="w-full max-w-[420px]"
        >
          {/* Mobile brand */}
          <div className="mb-6 flex items-center gap-3 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border-2 border-primary bg-primary text-primary-foreground">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <p className="text-lg font-extrabold tracking-tight">CipherChat</p>
          </div>

          <div className="rounded-xl border-2 border-border bg-surface p-6 nb-shadow">
            {/* Tabs */}
            <div className="mb-6 grid grid-cols-2 gap-1 rounded-xl border-2 border-border bg-background p-1">
              {(['login', 'register'] as Mode[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => switchMode(option)}
                  className={cn(
                    'relative flex items-center justify-center gap-2 rounded-lg py-2 text-xs font-bold uppercase tracking-[0.06em] transition-colors',
                    mode === option ? 'text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {mode === option && (
                    <motion.span
                      layoutId="auth-tab"
                      transition={springSoft}
                      className="absolute inset-0 rounded-lg bg-primary"
                    />
                  )}
                  <span className="relative flex items-center gap-2">
                    {option === 'login' ? <Lock className="h-3.5 w-3.5" /> : <UserPlus className="h-3.5 w-3.5" />}
                    {option === 'login' ? 'Sign in' : 'Register'}
                  </span>
                </button>
              ))}
            </div>

            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              <Input
                ref={usernameRef}
                label="Username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                spellCheck={false}
                maxLength={24}
                placeholder="abhishek"
                icon={<User className="h-4 w-4" />}
                hint={mode === 'register' ? '3–24 characters · letters, digits, underscore' : undefined}
                disabled={disabled}
              />

              <Input
                label="Password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                maxLength={128}
                placeholder="••••••••"
                icon={<Lock className="h-4 w-4" />}
                disabled={disabled}
                trailing={
                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:text-foreground"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                }
              />

              {mode === 'register' && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.18 }}
                >
                  <Input
                    label="Confirm password"
                    type={showPassword ? 'text' : 'password'}
                    value={confirm}
                    onChange={(event) => setConfirm(event.target.value)}
                    autoComplete="new-password"
                    maxLength={128}
                    placeholder="••••••••"
                    icon={<Lock className="h-4 w-4" />}
                    disabled={disabled}
                  />
                </motion.div>
              )}

              {message && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-start gap-2 rounded-lg border-2 border-danger/40 bg-danger/10 p-2.5"
                  role="alert"
                >
                  <p className="text-[11px] font-medium leading-relaxed text-danger">
                    {message}
                    {cooldown > 0 && ` Try again in ${cooldown}s.`}
                  </p>
                </motion.div>
              )}

              <Button
                type="submit"
                size="lg"
                loading={chat.busy}
                disabled={disabled}
                className="w-full"
              >
                {!chat.busy && (
                  <>
                    {mode === 'login' ? 'Sign in' : 'Create account'}
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </Button>
            </form>
          </div>

          {/* Connection state */}
          <div className="mt-4 flex items-center justify-between px-1 font-mono text-[10px] uppercase tracking-[0.08em]">
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <Server className="h-3 w-3" />
              {chat.serverUrl.replace('wss://', '')}
            </span>
            <span
              className={cn(
                'flex items-center gap-1.5',
                connected ? 'text-primary' : 'text-muted-foreground',
              )}
            >
              {connected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
              {connected
                ? 'Connected'
                : chat.status === 'reconnecting'
                  ? 'Reconnecting'
                  : 'Offline'}
            </span>
          </div>
        </motion.div>
      </div>
    </div>
  );
};
