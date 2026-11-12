import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}
    >
      {children}
    </svg>
  );
}

export const SearchIcon = (p: IconProps) => <Icon {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></Icon>;
export const HomeIcon = (p: IconProps) => <Icon {...p}><path d="M3 11 12 3l9 8" /><path d="M5 10v10h14V10" /></Icon>;
export const CompassIcon = (p: IconProps) => <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5-5 2 2-5z" /></Icon>;
export const LibraryIcon = (p: IconProps) => <Icon {...p}><path d="M5 4v16M10 4v16" /><path d="m14.5 5 4.5 14" /></Icon>;
export const SunIcon = (p: IconProps) => <Icon {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5" /></Icon>;
export const MoonIcon = (p: IconProps) => <Icon {...p}><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" /></Icon>;
export const StarIcon = (p: IconProps) => <Icon fill="currentColor" stroke="none" {...p}><path d="m12 2.5 2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5L2.5 9.4l6.6-.9z" /></Icon>;
export const BookmarkIcon = (p: IconProps) => <Icon {...p}><path d="M6 3h12v18l-6-4.5L6 21z" /></Icon>;
export const ChevronLeft = (p: IconProps) => <Icon {...p}><path d="m15 5-7 7 7 7" /></Icon>;
export const ChevronRight = (p: IconProps) => <Icon {...p}><path d="m9 5 7 7-7 7" /></Icon>;
export const PlayIcon = (p: IconProps) => <Icon fill="currentColor" stroke="none" {...p}><path d="M7 4.5v15l13-7.5z" /></Icon>;
export const SettingsIcon = (p: IconProps) => <Icon {...p}><path d="M4 7h10M18 7h2M4 17h2M10 17h10" /><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /></Icon>;
export const CloseIcon = (p: IconProps) => <Icon {...p}><path d="M6 6l12 12M18 6 6 18" /></Icon>;
export const CheckIcon = (p: IconProps) => <Icon {...p}><path d="m5 12.5 4.5 4.5L19 7.5" /></Icon>;
export const EyeIcon = (p: IconProps) => <Icon {...p}><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></Icon>;
export const SortIcon = (p: IconProps) => <Icon {...p}><path d="M7 4v16M7 20l-3-3M7 20l3-3M17 20V4M17 4l-3 3M17 4l3 3" /></Icon>;
export const ExpandIcon = (p: IconProps) => <Icon {...p}><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></Icon>;

export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" width="28" height="28" className={className} aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="var(--accent)" />
      <path d="M16 6c3.6 4.6 6 7.800 6 11a6 6 0 0 1-12 0c0-3.200 2.400-6.400 6-11z" fill="var(--accent-ink)" />
      <circle cx="13.800" cy="17.500" r="1.500" fill="var(--accent)" />
    </svg>
  );
}
