import React from 'react';
import { motion, type HTMLMotionProps } from 'framer-motion';
import { Loader2 } from 'lucide-react';
import { cn } from '../../lib/format';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends Omit<HTMLMotionProps<'button'>, 'children'> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children?: React.ReactNode;
}

const variants: Record<Variant, string> = {
  primary:
    'bg-primary text-primary-foreground border-2 border-primary nb-shadow hover:brightness-105 disabled:bg-muted disabled:text-muted-foreground disabled:border-border disabled:shadow-none',
  secondary:
    'bg-elevated text-foreground border-2 border-border nb-shadow-sm hover:border-border-strong hover:bg-card disabled:opacity-50',
  ghost:
    'bg-transparent text-muted-foreground border-2 border-transparent hover:text-foreground hover:bg-elevated disabled:opacity-40',
  danger:
    'bg-danger/15 text-danger border-2 border-danger/40 hover:bg-danger/25 disabled:opacity-50',
};

const sizes: Record<Size, string> = {
  sm: 'h-8 px-3 text-xs gap-1.5 rounded-lg',
  md: 'h-10 px-4 text-sm gap-2 rounded-xl',
  lg: 'h-12 px-5 text-sm gap-2 rounded-xl',
};

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  loading = false,
  className,
  children,
  disabled,
  ...rest
}) => (
  <motion.button
    type="button"
    whileTap={{ scale: 0.97 }}
    transition={{ type: 'spring', stiffness: 500, damping: 30 }}
    disabled={disabled || loading}
    className={cn(
      'nb-press inline-flex items-center justify-center font-bold select-none',
      'disabled:cursor-not-allowed',
      variants[variant],
      sizes[size],
      className,
    )}
    {...rest}
  >
    {loading && <Loader2 className="w-4 h-4 animate-spin" aria-hidden />}
    {children}
  </motion.button>
);
