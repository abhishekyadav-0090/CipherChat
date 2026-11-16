import React, { useId } from 'react';
import { cn } from '../../lib/format';

interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'ref'> {
  ref?: React.Ref<HTMLInputElement>;
  label?: string;
  error?: string | null;
  hint?: string;
  icon?: React.ReactNode;
  trailing?: React.ReactNode;
}

export const Input: React.FC<InputProps> = ({
  label,
  error,
  hint,
  icon,
  trailing,
  className,
  id,
  ref,
  ...rest
}) => {
  const generatedId = useId();
  const inputId = id ?? generatedId;

  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.08em] text-muted-foreground"
        >
          {label}
        </label>
      )}
      <div className="relative">
        {icon && (
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">
            {icon}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={!!error}
          aria-describedby={error ? `${inputId}-error` : undefined}
          className={cn(
            'h-11 w-full rounded-xl border-2 bg-surface text-sm text-foreground',
            'placeholder:text-muted-foreground/60 transition-colors',
            'focus:outline-none focus:border-primary focus:bg-card',
            icon ? 'pl-10' : 'pl-3',
            trailing ? 'pr-10' : 'pr-3',
            error ? 'border-danger' : 'border-border',
            className,
          )}
          {...rest}
        />
        {trailing && (
          <span className="absolute right-2 top-1/2 -translate-y-1/2">{trailing}</span>
        )}
      </div>
      {error ? (
        <p id={`${inputId}-error`} className="mt-1.5 text-[11px] font-medium text-danger">
          {error}
        </p>
      ) : hint ? (
        <p className="mt-1.5 text-[11px] text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
};
