import type { Transition, Variants } from 'framer-motion';

/*
 * Shared motion language.
 *
 * Rules the app follows:
 *  - motion explains a change of state, it never delays the user
 *  - nothing animates for longer than ~350 ms except deliberate springs
 *  - every preset is skipped when the OS asks for reduced motion
 *    (`useReducedMotion` in the component decides)
 */

export const springSoft: Transition = { type: 'spring', stiffness: 260, damping: 26, mass: 0.7 };
export const springSnappy: Transition = { type: 'spring', stiffness: 420, damping: 30 };
export const easeOut: Transition = { duration: 0.22, ease: [0.2, 0.8, 0.2, 1] };

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: easeOut },
  exit: { opacity: 0, y: -6, transition: { duration: 0.15 } },
};

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: easeOut },
  exit: { opacity: 0, transition: { duration: 0.15 } },
};

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.96, y: 8 },
  show: { opacity: 1, scale: 1, y: 0, transition: springSoft },
  exit: { opacity: 0, scale: 0.97, y: 6, transition: { duration: 0.14 } },
};

export const slideFromRight: Variants = {
  hidden: { opacity: 0, x: 24 },
  show: { opacity: 1, x: 0, transition: springSoft },
  exit: { opacity: 0, x: 24, transition: { duration: 0.16 } },
};

export const listStagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.035, delayChildren: 0.02 } },
};

export const bubbleIn: Variants = {
  hidden: { opacity: 0, y: 8, scale: 0.98 },
  show: { opacity: 1, y: 0, scale: 1, transition: springSnappy },
};
