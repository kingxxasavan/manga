// Drives the deck in a real browser against a real, supervised Anexis server
// whose model is scripted. Run: node tests/ui/deck.mjs   (pytest runs it too)
//
// Needs Playwright with a Chromium it can launch. Screenshots go to the
// folder named in DECK_SHOTS when it is set.

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { cpSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");
const TOKEN = "deck-test-token";
const shots = process.env.DECK_SHOTS;
const python = process.env.DECK_PYTHON || "python3";

const freePort = () => new Promise((resolve) => {
  const probe = createServer().listen(0, "127.0.0.1", () => {
    const { port } = probe.address();
    probe.close(() => resolve(port));
  });
});

// A scratch copy of the deck and a scratch "code" folder, so the live editing
// checks can change files without touching the real ones.
const home = mkdtempSync(join(tmpdir(), "anexis-deck-"));
const ui = join(home, "ui"), code = join(home, "code");
cpSync(join(repo, "ui"), ui, { recursive: true });
mkdirSync(code);
writeFileSync(join(code, "part.py"), "x = 1\n");
mkdirSync(join(home, "workspace", "my föld er"), { recursive: true });
writeFileSync(join(home, "workspace", "my föld er", "notes ünï.txt"), "hello");

const port = await freePort();
const base = `http://127.0.0.1:${port}`;
const lines = [];
const supervisor = spawn(python, [join(here, "supervise.py"), home, String(port), code, ui], { cwd: repo });
supervisor.stdout.on("data", (chunk) => lines.push(...String(chunk).split("\n").filter(Boolean)));
supervisor.stderr.on("data", (chunk) => process.env.DECK_DEBUG && process.stderr.write(chunk));

const until = async (what, check, seconds = 40) => {
  const deadline = Date.now() + seconds * 1000;
  for (;;) {
    const value = await check();
    if (value) return value;
    if (Date.now() > deadline) throw new Error(`Timed out waiting for ${what}`);
    await new Promise((r) => setTimeout(r, 100));
  }
};
const states = () => lines.map((line) => (line.startsWith("ANEXIS_READY") ? "ready" : JSON.parse(line.slice(line.indexOf(" "))).state));

let browser, failed = 0, passed = 0;
const problems = [];
async function step(name, run) {
  try {
    await run();
    passed++;
    console.log(`  ok    ${name}`);
  } catch (error) {
    failed++;
    console.log(`  FAIL  ${name}\n        ${String(error.message).split("\n").join("\n        ")}`);
  }
}

try {
  await until("the brain to start", () => states().includes("ready"), 90);
  browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));
  page.on("pageerror", (e) => problems.push(`page error: ${e.message}`));
  const shot = async (name) => shots && page.screenshot({ path: join(shots, `${name}.png`) });
  const sendChat = async (text) => {
    await page.fill("#input", text);
    await page.keyboard.press("Enter");
  };
  const lastReply = () => page.locator(".msg.ai").last();

  await step("without the token the deck stays locked", async () => {
    await page.goto(`${base}/ui/`);
    await page.waitForSelector(".sheet h2:has-text('Locked')");
    assert.equal(await page.locator(".chat-empty").count(), 0);
  });

  await step("the token in the link unlocks it and leaves the address bar", async () => {
    await page.goto(`${base}/ui/#token=${TOKEN}`);
    await page.reload();
    await page.waitForSelector("#boot:not([hidden])");
    await shot("01-boot");
    assert.equal(new URL(page.url()).hash, "");
  });

  await step("a new install opens setup after the boot sequence", async () => {
    await page.waitForSelector(".sheet .cards", { timeout: 15000 });
    assert.equal(await page.locator("#boot").isHidden(), true);
    assert.equal(await page.locator(".card").count(), 4);
    assert.equal(await page.locator(".card em").innerText(), "BEST FIT FOR THIS PC");
    await shot("02-setup-preset");
  });

  await step("setup saves the choices and keys, then restarts the brain with them", async () => {
    await page.click('.card:has-text("Cloud")');
    await page.click(".sheet-foot .primary");
    await page.fill(".sheet input[type=text]", "Nex");
    assert.equal(await page.locator('.card[aria-pressed="true"] b').innerText(), "FULL CONTROL");
    await shot("03-setup-options");
    await page.click(".sheet-foot .primary");
    for (const box of await page.$$(".sheet .check-row input:not(:disabled)")) await box.uncheck();
    await shot("04-setup-downloads");
    await page.click(".sheet-foot .primary");
    await page.fill(".keyrow input >> nth=0", "nvapi-abcdefghijklmnop");
    await page.fill(".keyrow input >> nth=7", 'od"d key');
    await shot("05-setup-keys");
    await page.click(".sheet-foot .primary");
    await page.waitForSelector('.sheet-foot .primary:has-text("Done")', { timeout: 60000 });
    await shot("06-setup-done");
    assert.match(await page.locator(".sheet-body").innerText(), /All set/);
    assert.match(await page.locator(".sheet-body").innerText(), /EXA_API_KEY: That has a space/);
    const env = readFileSync(join(home, "home", ".env"), "utf8");
    assert.match(env, /NVIDIA_API_KEY=nvapi-abcdefghijklmnop/);
    assert.match(readFileSync(join(home, "home", "anexis.toml"), "utf8"), /control = "full"/);
    await page.click(".sheet-foot .primary");
    await page.waitForSelector(".chat-empty");
    assert.equal(await page.locator("#brand-name").innerText(), "NEX");
    assert.equal(await page.locator("#control").innerText(), "FULL CONTROL");
    assert.equal(await page.locator(".sheet").isVisible(), false);
  });

  await step("a message streams a reply with formatting", async () => {
    await sendChat("hi there");
    await page.waitForSelector(".msg.ai .msg-foot");
    assert.equal(await lastReply().locator(".body b").innerText(), "here");
    assert.equal(await lastReply().locator(".body li").count(), 2);
    assert.equal(await lastReply().locator(".body code").innerText(), "/help");
    assert.equal(await page.locator(".cursor").count(), 0);
  });

  await step("under full control a tool runs without asking and shows in the activity feed", async () => {
    await sendChat("run it");
    await page.waitForSelector('.tool-chip[data-status="done"]');
    await lastReply().locator(".msg-foot").waitFor();
    assert.equal(await page.locator(".confirm").count(), 0);
    assert.match(await lastReply().locator(".body").innerText(), /deck-says-hi/);
    assert.match(await lastReply().locator(".msg-foot").innerText(), /used: run_shell/);
    const row = page.locator('.act[data-status="done"]').first();
    await row.waitFor();
    assert.match(await row.innerText(), /run_shell/);
    await row.click();
    assert.match(await page.locator(".act-out").first().innerText(), /deck-says-hi/);
    await shot("07-chat");
  });

  await step("STOP ends a running job and the chat carries on", async () => {
    await sendChat("wait a while");
    await page.waitForSelector('.tool-chip[data-status="running"]');
    assert.equal(await page.locator("#stop").isEnabled(), true);
    await page.click("#stop");
    await page.waitForSelector("#stop:disabled", { timeout: 15000 });
    assert.match(await lastReply().innerText(), /stopped/);
    await page.locator('.act[data-status="stopped"]').first().waitFor();
    await sendChat("still there?");
    await page.waitForFunction(() => document.querySelectorAll(".msg.ai .msg-foot").length >= 3);
  });

  await step("ask first mode waits for a yes before a risky tool runs", async () => {
    await page.click("#control");
    await page.waitForFunction(() => document.querySelector("#control").innerText === "ASK FIRST");
    await sendChat("run it again");
    await page.waitForSelector(".confirm");
    await shot("08-ask-first");
    assert.match(await page.locator(".confirm").innerText(), /run_shell wants to run/);
    await page.click(".confirm .primary");
    await page.waitForSelector(".confirm", { state: "detached" });
    await lastReply().locator(".msg-foot").waitFor();
    await page.click("#control");
    await page.click('.sheet-foot .primary:has-text("Turn on full control")');
    await page.waitForFunction(() => document.querySelector("#control").innerText === "FULL CONTROL");
  });

  await step("slash commands work and unknown ones say so", async () => {
    await page.fill("#input", "/re");
    assert.equal(await page.locator("#suggest button").count(), 1);
    await sendChat("/remember I like the ember theme");
    await page.locator('.mem:has-text("I like the ember theme")').waitFor();
    await sendChat("/theme ember");
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "ember");
    await sendChat("/nope");
    assert.match(await page.locator(".note").last().innerText(), /No command \/nope/);
    await sendChat("/theme ion");
  });

  await step("memory can be searched and forgotten", async () => {
    await page.fill("#mem-search", "ember");
    await page.waitForFunction(() => document.querySelectorAll(".mem").length === 1);
    const forget = page.locator(".mem button");
    await page.locator(".mem").hover();
    await forget.click();
    assert.equal(await forget.innerText(), "SURE?");
    await forget.click();
    await page.waitForSelector(".side-list .empty");
    await page.fill("#mem-search", "");
  });

  await step("the tools panel lists what Anexis can use", async () => {
    await page.click('.tabs [data-right="tools"]');
    await page.locator('.tool b:text-is("run_shell")').waitFor();
    await page.fill('#tools input[type="search"]', "mouse");
    await page.waitForFunction(() => [...document.querySelectorAll(".tool b")].every((b) => /mouse/.test(b.parentNode.innerText)));
    await page.click('.tabs [data-right="memory"]');
  });

  await step("the files panel browses folders with odd names", async () => {
    await page.click('.roots .chip:has-text("Workspace")');
    await page.click('.tile:has-text("my föld er")');
    await page.locator('.tile:has-text("notes ünï.txt")').waitFor();
    assert.match(await page.locator("#files-crumbs").innerText(), /my föld er$/);
    await page.click("#files-up");
    await page.locator('.tile:has-text("my föld er")').waitFor();
  });

  await step("the system panel shows live numbers", async () => {
    assert.match(await page.locator(".sys-head b").innerText(), /^\d+\s*%$/);
    assert.ok((await page.locator(".procs tr").count()) >= 3);
    assert.match(await page.locator("#sys-host").innerText(), /·/);
  });

  await step("the terminal is a real shell", async () => {
    await page.click('.tabs [data-center="terminal"]');
    await page.waitForSelector(".xterm-rows");
    await page.waitForTimeout(800);
    await page.keyboard.type("echo term-$((40+2))\n");
    await page.waitForFunction(() => document.querySelector(".xterm-rows").innerText.includes("term-42"));
    await shot("09-terminal");
    await page.click('.tabs [data-center="chat"]');
  });

  await step("checkup, about me and the app screen open and close", async () => {
    await page.click('[data-open="doctor"]');
    await page.waitForSelector(".checkline");
    await shot("10-checkup");
    await page.keyboard.press("Escape");
    await page.click('[data-open="about"]');
    await page.fill(".sheet .field input >> nth=0", "Sam");
    await page.click('.sheet-foot .primary:has-text("Save")');
    await page.waitForSelector(".sheet", { state: "hidden" });
    await page.locator('.mem:has-text("Name: Sam")').waitFor();
    await page.click('[data-open="app"]');
    await page.waitForSelector(".swatch");
    await shot("11-app");
    await page.click('.swatch:has-text("verdant")');
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "verdant");
    await page.click('.swatch:has-text("ion")');
    await page.keyboard.press("Escape");
    assert.equal(await page.locator(".sheet").isVisible(), false);
  });

  await step("editing a stylesheet restyles the open deck without a reload", async () => {
    await page.evaluate(() => { window.__stayed = true; });
    writeFileSync(join(ui, "deck.css"), readFileSync(join(ui, "deck.css"), "utf8") + "\n.brand-name { letter-spacing: 9px; }\n");
    await page.waitForFunction(() => getComputedStyle(document.querySelector(".brand-name")).letterSpacing === "9px", null, { timeout: 15000 });
    assert.equal(await page.evaluate(() => window.__stayed), true);
  });

  await step("editing a script reloads the deck and the conversation is still there", async () => {
    writeFileSync(join(ui, "js", "dom.js"), readFileSync(join(ui, "js", "dom.js"), "utf8") + "\n// edited\n");
    await page.waitForFunction(() => window.__stayed === undefined, null, { timeout: 15000 });
    await page.waitForSelector(".msg.ai");
    assert.ok((await page.locator(".msg").count()) >= 6);
    assert.equal(await page.locator("#boot").isHidden(), true);
  });

  await step("a Python file with a mistake is held back and the deck says why", async () => {
    writeFileSync(join(code, "part.py"), "def broken(:\n");
    await page.waitForSelector(".banner.bad");
    assert.match(await page.locator("#banner").innerText(), /part\.py line 1/);
    assert.equal(states().includes("held"), true);
    await sendChat("still working?");
    await page.waitForFunction(() => document.querySelector(".msg.ai:last-of-type .msg-foot"));
    await shot("12-held");
  });

  await step("fixing the file restarts the brain and the deck reconnects by itself", async () => {
    const before = states().filter((s) => s === "running").length;
    writeFileSync(join(code, "part.py"), "def fixed():\n    return 1\n");
    await until("the brain to restart", () => states().filter((s) => s === "running").length > before);
    await page.waitForSelector("#banner", { state: "hidden", timeout: 30000 });
    await sendChat("back?");
    await page.waitForFunction(() => /I am here/.test(document.querySelector(".msg.ai:last-of-type")?.innerText || ""), null, { timeout: 30000 });
  });

  await step("a phone sized window shows one panel at a time with no sideways scroll", async () => {
    await page.setViewportSize({ width: 390, height: 800 });
    await page.waitForTimeout(300);
    for (const view of ["chat", "terminal", "system", "memory", "tools", "files", "activity"]) {
      await page.click(`.views [data-view="${view}"]`);
      await page.waitForTimeout(150);
      const [wide, shown] = await page.evaluate(() => [
        document.documentElement.scrollWidth - innerWidth,
        [...document.querySelectorAll(".panel")].filter((p) => p.offsetParent).length,
      ]);
      assert.ok(wide <= 0, `${view} is ${wide}px too wide`);
      assert.equal(shown, 1, `${view} shows ${shown} panels`);
    }
    await page.click('.views [data-view="chat"]');
    await shot("13-phone");
    await page.click('[data-open="setup"]');
    await page.waitForSelector(".sheet .cards");
    assert.ok((await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 0);
    await page.keyboard.press("Escape");
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  await step("the wide layout fills the window with no page scroll", async () => {
    await page.waitForTimeout(300);
    const [tall, wide] = await page.evaluate(() => [document.documentElement.scrollHeight - innerHeight, document.documentElement.scrollWidth - innerWidth]);
    assert.ok(tall <= 0 && wide <= 0, `page scrolls by ${wide}x${tall}`);
    await shot("14-deck");
  });

  await step("nothing was logged as an error along the way", async () => {
    // The brain restarts in this run on purpose, and a request in flight at that
    // moment fails. Those are expected. Anything else is a bug.
    const real = problems.filter((p) => !/Failed to load resource|net::ERR|Failed to fetch/.test(p));
    assert.deepEqual(real, []);
  });
} finally {
  await browser?.close();
  supervisor.kill("SIGINT");
  await new Promise((resolve) => { supervisor.on("exit", resolve); setTimeout(resolve, 15000); });
}

console.log(`\n  ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
