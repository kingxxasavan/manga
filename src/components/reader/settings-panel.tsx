"use client";

import { useEffect, useRef } from "react";
import {
  BACKGROUNDS, DEFAULT_SETTINGS, type Background, type Direction, type Fit, type Mode, type ReaderSettings,
} from "@/lib/reader/logic";
import { CheckIcon, CloseIcon } from "../icons";

interface Option<T extends string> { value: T; label: string }

function Segmented<T extends string>({ label, value, options, onChange, hint }: {
  label: string; value: T; options: Option<T>[]; onChange: (value: T) => void; hint?: string;
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-xs font-bold uppercase tracking-widest text-white/55">{label}</legend>
      <div className="grid auto-cols-fr grid-flow-col gap-1 rounded-2xl bg-white/[0.07] p-1">
        {options.map((option) => (
          <button
            key={option.value} type="button" aria-pressed={value === option.value}
            onClick={() => onChange(option.value)}
            className={`rounded-xl px-2 py-2 text-sm font-semibold transition active:scale-[0.97] ${value === option.value ? "bg-accent text-accent-ink" : "text-white/75 hover:bg-white/10 hover:text-white"}`}
          >
            {option.label}
          </button>
        ))}
      </div>
      {hint && <p className="mt-1.5 text-xs text-white/50">{hint}</p>}
    </fieldset>
  );
}

function Slider({ label, value, min, max, step, unit, onChange }: {
  label: string; value: number; min: number; max: number; step: number; unit: string; onChange: (value: number) => void;
}) {
  return (
    <label className="block">
      <span className="mb-2 flex items-center justify-between text-xs font-bold uppercase tracking-widest text-white/55">
        {label}
        <span className="font-semibold normal-case tracking-normal text-white/85">{value}{unit}</span>
      </span>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} className="range w-full"
      />
    </label>
  );
}

const MODES: Option<ReaderSettings["mode"]>[] = [
  { value: "auto", label: "Auto" }, { value: "strip", label: "Strip" },
  { value: "single", label: "Single" }, { value: "double", label: "Double" },
];
const DIRECTIONS: Option<ReaderSettings["direction"]>[] = [
  { value: "auto", label: "Auto" }, { value: "rtl", label: "Right to left" }, { value: "ltr", label: "Left to right" },
];
const FITS: Option<Fit>[] = [
  { value: "height", label: "Height" }, { value: "width", label: "Width" }, { value: "original", label: "Original" },
];
const MODE_NAME: Record<Mode, string> = { strip: "long strip", single: "single page", double: "double page" };
const DIRECTION_NAME: Record<Direction, string> = { rtl: "right to left", ltr: "left to right" };

interface Props {
  settings: ReaderSettings;
  mode: Mode;
  direction: Direction;
  onChange: (patch: Partial<ReaderSettings>) => void;
  onClose: () => void;
}

export function SettingsPanel({ settings, mode, direction, onChange, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => closeRef.current?.focus(), []);

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Reader settings">
      <button type="button" aria-label="Close settings" onClick={onClose} className="absolute inset-0 cursor-default bg-black/50" />
      <aside className="rise absolute inset-x-0 bottom-0 max-h-[85dvh] overflow-y-auto rounded-t-3xl border-t border-white/10 bg-[#15161b] p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] text-white shadow-2xl sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none sm:w-[23rem] sm:rounded-none sm:border-l sm:border-t-0">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-xl font-extrabold">Reader settings</h2>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close settings" className="grid size-10 place-items-center rounded-full hover:bg-white/10">
            <CloseIcon />
          </button>
        </div>

        <div className="space-y-6">
          <Segmented
            label="Reading mode" value={settings.mode} options={MODES} onChange={(v) => onChange({ mode: v })}
            hint={settings.mode === "auto" ? `Auto uses ${MODE_NAME[mode]} for this series.` : undefined}
          />

          {mode !== "strip" && (
            <>
              <Segmented
                label="Direction" value={settings.direction} options={DIRECTIONS} onChange={(v) => onChange({ direction: v })}
                hint={settings.direction === "auto" ? `Auto reads ${DIRECTION_NAME[direction]} for this series.` : undefined}
              />
              <Segmented label="Fit page to" value={settings.fit} options={FITS} onChange={(v) => onChange({ fit: v })} />
            </>
          )}

          {mode === "strip" && (
            <>
              <Slider label="Strip width" value={settings.zoom} min={40} max={100} step={5} unit="%" onChange={(v) => onChange({ zoom: v })} />
              <Slider label="Gap between pages" value={settings.gap} min={0} max={48} step={4} unit="px" onChange={(v) => onChange({ gap: v })} />
            </>
          )}

          <fieldset>
            <legend className="mb-2 text-xs font-bold uppercase tracking-widest text-white/55">Background</legend>
            <div className="grid grid-cols-4 gap-2">
              {(Object.keys(BACKGROUNDS) as Background[]).map((key) => {
                const bg = BACKGROUNDS[key];
                const active = settings.background === key;
                return (
                  <button
                    key={key} type="button" aria-pressed={active} onClick={() => onChange({ background: key })}
                    className={`rounded-2xl p-1.5 text-xs font-semibold transition ${active ? "bg-white/10 text-white ring-2 ring-accent" : "text-white/65 hover:bg-white/[0.06]"}`}
                  >
                    <span className="mb-1.5 grid h-10 place-items-center rounded-xl border border-white/15" style={{ background: bg.color, color: bg.dark ? "#fff" : "#111" }}>
                      {active && <CheckIcon width={18} height={18} />}
                    </span>
                    {bg.label}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <label className="flex cursor-pointer items-center justify-between gap-4 rounded-2xl bg-white/[0.07] p-4">
            <span>
              <span className="block text-sm font-semibold">Auto continue</span>
              <span className="block text-xs text-white/55">In page modes, go straight into the next chapter after the last page.</span>
            </span>
            <input
              type="checkbox" role="switch" checked={settings.autoContinue}
              onChange={(e) => onChange({ autoContinue: e.target.checked })}
              className="peer sr-only"
            />
            <span className="relative h-7 w-12 shrink-0 rounded-full bg-white/20 transition peer-checked:bg-accent peer-focus-visible:ring-2 peer-focus-visible:ring-accent after:absolute after:left-1 after:top-1 after:size-5 after:rounded-full after:bg-white after:transition peer-checked:after:translate-x-5" />
          </label>

          <div className="rounded-2xl border border-white/10 p-4 text-xs leading-relaxed text-white/60">
            <p className="mb-1 font-bold uppercase tracking-widest text-white/55">Shortcuts</p>
            <p>Arrow keys or space turn pages. Tap the sides of a page to turn it, the middle for the menu, or swipe.</p>
            <p className="mt-1"><kbd className="font-semibold text-white/85">N</kbd> and <kbd className="font-semibold text-white/85">P</kbd> change chapter, <kbd className="font-semibold text-white/85">M</kbd> toggles the menu, <kbd className="font-semibold text-white/85">F</kbd> goes fullscreen.</p>
          </div>

          <button
            type="button" onClick={() => onChange(DEFAULT_SETTINGS)}
            className="w-full rounded-2xl border border-white/15 py-3 text-sm font-semibold text-white/80 transition hover:border-white/40 hover:text-white"
          >
            Reset to defaults
          </button>
        </div>
      </aside>
    </div>
  );
}
