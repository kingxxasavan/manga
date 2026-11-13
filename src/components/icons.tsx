import type { SVGProps } from "react";
import type { Service } from "@/lib/services";

type P = SVGProps<SVGSVGElement>;
const Icon = ({ children, ...p }: P) => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...p}>
    {children}
  </svg>
);

export const ArrowRight = (p: P) => <Icon {...p}><path d="M5 12h14M13 6l6 6-6 6" /></Icon>;
export const ArrowLeft = (p: P) => <Icon {...p}><path d="M19 12H5M11 6l-6 6 6 6" /></Icon>;
export const Check = (p: P) => <Icon {...p}><path d="m5 12.500 4.500 4.500L19 7.500" /></Icon>;
export const Minus = (p: P) => <Icon {...p}><path d="M6 12h12" /></Icon>;
export const Plus = (p: P) => <Icon {...p}><path d="M12 6v12M6 12h12" /></Icon>;
export const Sun = (p: P) => <Icon {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.500 1.500M17.500 17.500 19 19M5 19l1.500-1.500M17.500 6.500 19 5" /></Icon>;
export const Moon = (p: P) => <Icon {...p}><path d="M20 14.500A8.500 8.500 0 0 1 9.500 4a8.500 8.500 0 1 0 10.500 10.500z" /></Icon>;
export const Lock = (p: P) => <Icon {...p}><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></Icon>;
export const Clock = (p: P) => <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Icon>;

const SERVICE_ICONS: Record<Service["icon"], React.ReactNode> = {
  globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.500 2.500 3.800 5.500 3.800 9s-1.300 6.500-3.800 9c-2.500-2.500-3.800-5.500-3.800-9S9.500 5.500 12 3z" /></>,
  pen: <><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="m13.500 6.500 4 4" /></>,
  palette: <><path d="M12 3a9 9 0 1 0 0 18c1.400 0 2-1 2-2 0-1.500-1-1.800-1-3 0-1 .800-2 2-2h2a4 4 0 0 0 4-4c0-4-4-7-9-7z" /><circle cx="7.500" cy="11" r="1" /><circle cx="11" cy="7.500" r="1" /><circle cx="15.500" cy="8.500" r="1" /></>,
  code: <><path d="m8 7-5 5 5 5M16 7l5 5-5 5M13.500 5l-3 14" /></>,
  sparkles: <><path d="M11 3l1.800 5.200L18 10l-5.200 1.800L11 17l-1.800-5.200L4 10l5.200-1.800z" /><path d="M18.500 15.500l.700 2 2 .700-2 .700-.700 2-.700-2-2-.700 2-.700z" /></>,
};

export function ServiceIcon({ name, ...p }: P & { name: Service["icon"] }) {
  return <Icon {...p}>{SERVICE_ICONS[name]}</Icon>;
}

export function Logo() {
  return (
    <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="var(--accent)" />
      <path d="M9 21.500 16 9l7 12.500M12 17h8" fill="none" stroke="var(--accent-ink)" strokeWidth="2.600" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
