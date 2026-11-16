import React from 'react';
import { cn, hueFor, initials } from '../../lib/format';

type Size = 'sm' | 'md' | 'lg' | 'xl';

interface AvatarProps {
  name: string;
  size?: Size;
  online?: boolean;
  showStatus?: boolean;
  square?: boolean;
  className?: string;
}

const sizes: Record<Size, string> = {
  sm: 'w-8 h-8 text-[11px]',
  md: 'w-10 h-10 text-xs',
  lg: 'w-12 h-12 text-sm',
  xl: 'w-16 h-16 text-lg',
};

export const Avatar: React.FC<AvatarProps> = ({
  name,
  size = 'md',
  online,
  showStatus = false,
  square = false,
  className,
}) => {
  const hue = hueFor(name);

  return (
    <div className={cn('relative shrink-0', className)}>
      <div
        className={cn(
          'flex items-center justify-center border-2 border-border font-extrabold select-none',
          square ? 'rounded-lg' : 'rounded-full',
          sizes[size],
        )}
        style={{
          background: `linear-gradient(140deg, hsl(${hue} 55% 22%), hsl(${(hue + 40) % 360} 60% 14%))`,
          color: `hsl(${hue} 90% 78%)`,
        }}
        aria-hidden
      >
        {initials(name)}
      </div>
      {showStatus && (
        <span
          className={cn(
            'absolute -bottom-0.5 -right-0.5 rounded-full border-2 border-background',
            size === 'sm' ? 'w-2.5 h-2.5' : 'w-3 h-3',
            online ? 'bg-online' : 'bg-muted-foreground/50',
          )}
          title={online ? 'Online' : 'Offline'}
        />
      )}
    </div>
  );
};
