import type { CSSProperties, ReactNode } from "react";
import type { Look } from "@/lib/templates";

/**
 * A small drawing of the website a customer is designing: their layout, colors,
 * text style, image style and name. It is a sketch of the look, not the real
 * site, and it has no hooks so it works on server pages too.
 *
 * Everything is sized in em from one container based font size, so the same
 * markup works as a thumbnail and as a large preview.
 */

type Props = { look: Look; name?: string; className?: string };

/** Grey lines standing in for body text. */
const Bars = ({ widths, style }: { widths: number[]; style?: CSSProperties }) => (
  <div style={{ display: "grid", gap: "0.45em", marginTop: "0.7em", ...style }}>
    {widths.map((w, i) => (
      <span key={i} style={{ display: "block", height: "0.5em", width: `${w}%`, borderRadius: "1em", background: "var(--p-muted)", opacity: 0.35 }} />
    ))}
  </div>
);

/** A stand in for an image, drawn in the chosen image style. */
function Picture({ kind, style, seed = 0 }: { kind: string; style?: CSSProperties; seed?: number }) {
  const base: CSSProperties = { position: "relative", overflow: "hidden", borderRadius: "0.9em", ...style };
  if (kind === "none") {
    return <div style={{ ...base, border: "0.12em solid color-mix(in srgb, var(--p-muted) 35%, transparent)", background: "var(--p-surface)" }} />;
  }
  if (kind === "abstract") {
    return (
      <div
        style={{
          ...base,
          background: `radial-gradient(circle at ${20 + seed * 23}% 25%, var(--p-accent), transparent 60%), radial-gradient(circle at ${80 - seed * 17}% 80%, color-mix(in srgb, var(--p-accent) 45%, var(--p-text)), transparent 62%), color-mix(in srgb, var(--p-accent) 22%, var(--p-surface))`,
        }}
      />
    );
  }
  if (kind === "illustration") {
    return (
      <div style={{ ...base, background: "color-mix(in srgb, var(--p-accent) 16%, var(--p-surface))" }}>
        <span style={{ position: "absolute", left: `${12 + seed * 9}%`, bottom: "-18%", width: "46%", aspectRatio: "1", borderRadius: "50%", background: "var(--p-accent)" }} />
        <span style={{ position: "absolute", right: "10%", top: "14%", width: "26%", aspectRatio: "1", borderRadius: "28%", background: "color-mix(in srgb, var(--p-accent) 45%, var(--p-text))", transform: `rotate(${12 + seed * 14}deg)` }} />
        <span style={{ position: "absolute", right: "30%", bottom: "12%", width: "14%", aspectRatio: "1", borderRadius: "50%", background: "var(--p-text)", opacity: 0.85 }} />
      </div>
    );
  }
  // photo: a soft landscape, the usual sign for "a photograph goes here"
  return (
    <div style={{ ...base, background: "linear-gradient(180deg, color-mix(in srgb, var(--p-accent) 30%, var(--p-surface)), color-mix(in srgb, var(--p-accent) 60%, var(--p-surface)))" }}>
      <span style={{ position: "absolute", right: `${14 + seed * 11}%`, top: "16%", width: "16%", aspectRatio: "1", borderRadius: "50%", background: "color-mix(in srgb, var(--p-surface) 85%, var(--p-accent))" }} />
      <svg viewBox="0 0 100 40" preserveAspectRatio="none" style={{ position: "absolute", left: 0, bottom: 0, width: "100%", height: "62%" }} aria-hidden="true">
        <path d="M0 40 L0 26 L22 10 L40 24 L58 6 L80 22 L100 12 L100 40 Z" fill="color-mix(in srgb, var(--p-accent) 78%, var(--p-text))" />
        <path d="M0 40 L0 32 L30 20 L52 31 L74 18 L100 30 L100 40 Z" fill="color-mix(in srgb, var(--p-accent) 45%, var(--p-text))" />
      </svg>
    </div>
  );
}

const Button = ({ children, ghost = false }: { children: ReactNode; ghost?: boolean }) => (
  <span
    style={{
      display: "inline-block", padding: "0.55em 1.1em", borderRadius: "2em", fontSize: "0.82em", fontWeight: 700, whiteSpace: "nowrap",
      background: ghost ? "transparent" : "var(--p-accent)", color: ghost ? "var(--p-text)" : "var(--p-accent-ink)",
      border: ghost ? "0.12em solid color-mix(in srgb, var(--p-muted) 50%, transparent)" : "0.12em solid var(--p-accent)",
    }}
  >
    {children}
  </span>
);

const Heading = ({ children, size = 2.3, style }: { children: ReactNode; size?: number; style?: CSSProperties }) => (
  <p style={{ fontFamily: "var(--p-heading)", fontWeight: "var(--p-weight)" as CSSProperties["fontWeight"], letterSpacing: "var(--p-tracking)", fontSize: `${size}em`, lineHeight: 1.05, overflowWrap: "anywhere", ...style }}>
    {children}
  </p>
);

const Card = ({ children, style }: { children: ReactNode; style?: CSSProperties }) => (
  <div style={{ background: "var(--p-surface)", borderRadius: "0.9em", padding: "0.9em", border: "0.1em solid color-mix(in srgb, var(--p-muted) 22%, transparent)", ...style }}>{children}</div>
);

function Nav({ name, links }: { name: string; links: string[] }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "1.2em", padding: "1em 1.6em", borderBottom: "0.1em solid color-mix(in srgb, var(--p-muted) 22%, transparent)" }}>
      <span style={{ fontFamily: "var(--p-heading)", fontWeight: 800, fontSize: "1em", letterSpacing: "var(--p-tracking)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "45%" }}>{name}</span>
      <span style={{ flex: 1 }} />
      {links.map((link) => <span key={link} style={{ fontSize: "0.72em", color: "var(--p-muted)", whiteSpace: "nowrap" }}>{link}</span>)}
    </div>
  );
}

function Layout({ look, name }: { look: Look; name: string }) {
  const img = look.imagery.id;
  const cta = look.template.cta;
  const pad: CSSProperties = { padding: "1.6em" };

  switch (look.template.id) {
    case "storefront":
      return (
        <>
          <Nav name={name} links={["Shop", "About", "Cart"]} />
          <div style={{ ...pad, display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: "1.4em", alignItems: "center" }}>
            <div>
              <Heading>New in at {name}</Heading>
              <Bars widths={[92, 70]} />
              <div style={{ marginTop: "1em" }}><Button>{cta}</Button></div>
            </div>
            <Picture kind={img} style={{ aspectRatio: "4 / 3" }} />
          </div>
          <div style={{ ...pad, paddingTop: 0, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.8em" }}>
            {[0, 1, 2, 3].map((i) => (
              <Card key={i} style={{ padding: "0.55em" }}>
                <Picture kind={img} seed={i + 1} style={{ aspectRatio: "1", borderRadius: "0.6em" }} />
                <Bars widths={[80, 45]} style={{ marginTop: "0.55em" }} />
              </Card>
            ))}
          </div>
        </>
      );
    case "portfolio":
      return (
        <>
          <Nav name={name} links={["Work", "About", "Contact"]} />
          <div style={{ ...pad, paddingBottom: "1em" }}>
            <Heading size={3}>{name}</Heading>
            <Bars widths={[55, 40]} />
          </div>
          <div style={{ ...pad, paddingTop: 0, display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr", gridTemplateRows: "repeat(2, 7em)", gap: "0.8em" }}>
            <Picture kind={img} style={{ gridRow: "span 2" }} />
            <Picture kind={img} seed={1} />
            <Picture kind={img} seed={2} />
            <Picture kind={img} seed={3} style={{ gridColumn: "span 2" }} />
          </div>
          <div style={{ ...pad, paddingTop: 0 }}><Button>{cta}</Button></div>
        </>
      );
    case "restaurant":
      return (
        <>
          <Nav name={name} links={["Menu", "Hours", "Find us"]} />
          <div style={{ position: "relative" }}>
            <Picture kind={img} style={{ height: "12.5em", borderRadius: 0 }} />
            <div style={{ position: "absolute", left: "1.6em", bottom: "1.2em", right: "1.6em" }}>
              <Card style={{ display: "inline-block", maxWidth: "70%" }}>
                <Heading size={1.9}>{name}</Heading>
                <div style={{ marginTop: "0.7em" }}><Button>{cta}</Button></div>
              </Card>
            </div>
          </div>
          <div style={{ ...pad, display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.6em" }}>
            {["Starters", "Mains"].map((title) => (
              <div key={title}>
                <Heading size={1.15} style={{ marginBottom: "0.6em" }}>{title}</Heading>
                {[78, 64, 70, 56].map((w, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1em", marginBottom: "0.7em" }}>
                    {/* the line needs a width of its own inside a flex row, or it collapses */}
                    <Bars widths={[w]} style={{ flex: 1, marginTop: 0 }} />
                    <span style={{ width: "1.6em", height: "0.5em", borderRadius: "1em", background: "var(--p-accent)", opacity: 0.7, flex: "none" }} />
                  </div>
                ))}
              </div>
            ))}
          </div>
        </>
      );
    case "launch":
      return (
        <>
          <Nav name={name} links={["Features", "Pricing"]} />
          <div style={{ ...pad, textAlign: "center", paddingBottom: "1.1em" }}>
            <span style={{ display: "inline-block", fontSize: "0.68em", fontWeight: 700, padding: "0.35em 0.9em", borderRadius: "2em", background: "color-mix(in srgb, var(--p-accent) 18%, transparent)", color: "var(--p-accent)" }}>Now open</span>
            <Heading size={2.9} style={{ margin: "0.35em auto 0", maxWidth: "88%" }}>{name}, made simple</Heading>
            <Bars widths={[62, 46]} style={{ justifyItems: "center" }} />
            <div style={{ marginTop: "1em", display: "flex", gap: "0.6em", justifyContent: "center" }}><Button>{cta}</Button><Button ghost>Learn more</Button></div>
          </div>
          <div style={{ ...pad, paddingTop: 0 }}><Picture kind={img} style={{ height: "9em" }} /></div>
          <div style={{ ...pad, paddingTop: 0, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.8em" }}>
            {[0, 1, 2].map((i) => <Card key={i}><span style={{ display: "block", width: "1.5em", height: "1.5em", borderRadius: "0.45em", background: "var(--p-accent)", marginBottom: "0.6em" }} /><Bars widths={[85, 60]} /></Card>)}
          </div>
        </>
      );
    case "blog":
      return (
        <>
          <Nav name={name} links={["Latest", "Topics", "About"]} />
          <div style={{ ...pad, display: "grid", gridTemplateColumns: "1.25fr 1fr", gap: "1.4em", alignItems: "center" }}>
            <Picture kind={img} style={{ aspectRatio: "16 / 10" }} />
            <div>
              <span style={{ fontSize: "0.68em", fontWeight: 700, color: "var(--p-accent)", textTransform: "uppercase", letterSpacing: "0.12em" }}>Featured</span>
              <Heading size={1.9} style={{ marginTop: "0.25em" }}>The latest from {name}</Heading>
              <Bars widths={[95, 88, 60]} />
              <div style={{ marginTop: "0.9em" }}><Button>{cta}</Button></div>
            </div>
          </div>
          <div style={{ ...pad, paddingTop: 0, display: "grid", gap: "0.7em" }}>
            {[0, 1, 2].map((i) => (
              <Card key={i} style={{ display: "grid", gridTemplateColumns: "4.2em 1fr", gap: "0.9em", alignItems: "center", padding: "0.6em" }}>
                <Picture kind={img} seed={i + 1} style={{ aspectRatio: "1", borderRadius: "0.55em" }} />
                <Bars widths={[70, 92, 40]} />
              </Card>
            ))}
          </div>
        </>
      );
    default:
      // business
      return (
        <>
          <Nav name={name} links={["Services", "About", "Contact"]} />
          <div style={{ ...pad, display: "grid", gridTemplateColumns: "1.15fr 1fr", gap: "1.4em", alignItems: "center" }}>
            <div>
              <Heading size={2.5}>{name}</Heading>
              <Bars widths={[95, 82, 55]} />
              <div style={{ marginTop: "1em", display: "flex", gap: "0.6em", flexWrap: "wrap" }}><Button>{cta}</Button><Button ghost>Our work</Button></div>
            </div>
            <Picture kind={img} style={{ aspectRatio: "5 / 4.4" }} />
          </div>
          <div style={{ ...pad, paddingTop: 0, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.8em" }}>
            {[0, 1, 2].map((i) => <Card key={i}><span style={{ display: "block", width: "1.5em", height: "1.5em", borderRadius: "50%", background: "var(--p-accent)", marginBottom: "0.6em" }} /><Bars widths={[80, 95, 60]} /></Card>)}
          </div>
        </>
      );
  }
}

export function SitePreview({ look, name, className = "" }: Props) {
  const { palette, font } = look;
  // Whatever the customer typed is only ever rendered as text, never as markup.
  const shownName = (name ?? "").trim().slice(0, 50) || "Your name here";
  const vars = {
    "--p-bg": palette.bg, "--p-surface": palette.surface, "--p-text": palette.text, "--p-muted": palette.muted,
    "--p-accent": palette.accent, "--p-accent-ink": palette.accentInk,
    "--p-heading": font.heading, "--p-weight": font.headingWeight, "--p-tracking": `${font.tracking}em`,
    containerType: "inline-size",
  } as CSSProperties;

  return (
    <div aria-hidden="true" className={`select-none overflow-hidden rounded-xl border border-line shadow-card ${className}`} style={vars}>
      {/* browser bar */}
      <div className="flex items-center gap-1 bg-surface-2 px-2 py-1.5">
        <span className="size-1.5 rounded-full bg-line" /><span className="size-1.5 rounded-full bg-line" /><span className="size-1.5 rounded-full bg-line" />
        <span className="ml-1.5 h-2 flex-1 rounded-full bg-surface" />
      </div>
      <div
        style={{
          fontSize: "2.35cqw", lineHeight: 1.35, aspectRatio: "16 / 12", overflow: "hidden",
          background: "var(--p-bg)", color: "var(--p-text)", fontFamily: font.body,
          transition: "background-color 300ms ease, color 300ms ease",
        }}
      >
        <Layout look={look} name={shownName} />
      </div>
    </div>
  );
}
