import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useChat } from './hooks/useChat';
import { AuthScreen } from './components/auth/AuthScreen';
import { AppShell } from './components/shell/AppShell';
import { Toasts } from './components/ui/Toasts';
import type { Accent } from './components/settings/SettingsView';

const ACCENT_CLASS: Record<Accent, string> = {
  lime: '',
  purple: 'accent-purple',
  cyan: 'accent-cyan',
  amber: 'accent-amber',
};

const ACCENT_KEY = 'cipherchat.accent';

function readAccent(): Accent {
  try {
    const stored = localStorage.getItem(ACCENT_KEY);
    if (stored === 'lime' || stored === 'purple' || stored === 'cyan' || stored === 'amber') {
      return stored;
    }
  } catch {
    /* storage may be blocked */
  }
  return 'lime';
}

export default function App() {
  const chat = useChat();
  const [accent, setAccent] = useState<Accent>(readAccent);

  // A colour preference is not a secret, so localStorage is the right place.
  useEffect(() => {
    try {
      localStorage.setItem(ACCENT_KEY, accent);
    } catch {
      /* ignore */
    }
  }, [accent]);

  const authenticated = Boolean(chat.session);

  return (
    <div className={`h-full w-full ${ACCENT_CLASS[accent]}`}>
      <AnimatePresence mode="wait">
        {authenticated ? (
          <motion.div
            key="app"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="h-full w-full"
          >
            <AppShell chat={chat} accent={accent} onAccentChange={setAccent} />
          </motion.div>
        ) : (
          <motion.div
            key="auth"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="h-full w-full"
          >
            <AuthScreen chat={chat} />
          </motion.div>
        )}
      </AnimatePresence>

      <Toasts notices={chat.notices} onDismiss={chat.dismissNotice} />
    </div>
  );
}
