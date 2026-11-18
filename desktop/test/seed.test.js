// Tests for the live copy (seed.js). Run: npm test

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");
const { loadFrame, resetLiveCopy, seedLiveCopy, seededVersion } = require("../seed.js");

function scratch() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "anexis-seed-"));
  const source = path.join(root, "resources", "source");
  fs.mkdirSync(path.join(source, "anexis", "__pycache__"), { recursive: true });
  fs.mkdirSync(path.join(source, "ui"));
  fs.mkdirSync(path.join(source, "desktop"));
  fs.writeFileSync(path.join(source, "anexis", "core.py"), "VERSION = 1\n");
  fs.writeFileSync(path.join(source, "anexis", "__pycache__", "core.pyc"), "junk");
  fs.writeFileSync(path.join(source, "ui", "index.html"), "<p>deck</p>");
  fs.writeFileSync(path.join(source, "desktop", "frame.js"), "module.exports = { start() { return 'shipped'; } };\n");
  return { root, source, live: path.join(root, "data", "Anexis", "app") };
}

test("the first launch copies the app's files into the live folder", () => {
  const { source, live } = scratch();
  const result = seedLiveCopy({ source, live, version: "0.2.0" });
  assert.equal(result.action, "seeded");
  assert.equal(fs.readFileSync(path.join(live, "anexis", "core.py"), "utf8"), "VERSION = 1\n");
  assert.equal(fs.existsSync(path.join(live, "ui", "index.html")), true);
  assert.equal(fs.existsSync(path.join(live, "anexis", "__pycache__")), false);
  assert.equal(seededVersion(live), "0.2.0");
});

test("the same version never touches a live copy that was edited", () => {
  const { source, live } = scratch();
  seedLiveCopy({ source, live, version: "0.2.0" });
  fs.writeFileSync(path.join(live, "anexis", "core.py"), "VERSION = 'edited by Claude'\n");
  fs.writeFileSync(path.join(live, "anexis", "extra.py"), "new = True\n");
  const result = seedLiveCopy({ source, live, version: "0.2.0" });
  assert.equal(result.action, "kept");
  assert.equal(fs.readFileSync(path.join(live, "anexis", "core.py"), "utf8"), "VERSION = 'edited by Claude'\n");
  assert.equal(fs.existsSync(path.join(live, "anexis", "extra.py")), true);
});

test("a new version moves the edited copy aside whole before replacing it", () => {
  const { source, live } = scratch();
  seedLiveCopy({ source, live, version: "0.2.0" });
  fs.writeFileSync(path.join(live, "anexis", "core.py"), "VERSION = 'edited by Claude'\n");
  fs.writeFileSync(path.join(source, "anexis", "core.py"), "VERSION = 2\n");
  const result = seedLiveCopy({ source, live, version: "0.3.0", now: new Date("2026-11-17T10:20:30Z") });
  assert.equal(result.action, "updated");
  assert.equal(path.basename(result.backup), "app-backup-0.2.0-20261117102030");
  assert.equal(fs.readFileSync(path.join(result.backup, "anexis", "core.py"), "utf8"), "VERSION = 'edited by Claude'\n");
  assert.equal(fs.readFileSync(path.join(live, "anexis", "core.py"), "utf8"), "VERSION = 2\n");
  assert.equal(seededVersion(live), "0.3.0");
});

test("a live folder with no version mark is backed up, not overwritten", () => {
  const { source, live } = scratch();
  fs.mkdirSync(path.join(live, "anexis"), { recursive: true });
  fs.writeFileSync(path.join(live, "anexis", "mine.py"), "keep = True\n");
  const result = seedLiveCopy({ source, live, version: "0.2.0", now: new Date("2026-11-17T10:20:30Z") });
  assert.equal(result.action, "updated");
  assert.match(path.basename(result.backup), /^app-backup-unknown-/);
  assert.equal(fs.existsSync(path.join(result.backup, "anexis", "mine.py")), true);
});

test("a half finished copy from a crash is thrown away, not used", () => {
  const { source, live } = scratch();
  fs.mkdirSync(`${live}.incoming`, { recursive: true });
  fs.writeFileSync(path.join(`${live}.incoming`, "stale.txt"), "old");
  seedLiveCopy({ source, live, version: "0.2.0" });
  assert.equal(fs.existsSync(path.join(live, "stale.txt")), false);
  assert.equal(fs.existsSync(`${live}.incoming`), false);
});

test("missing shipped files are reported instead of seeding an empty app", () => {
  const { root, live } = scratch();
  assert.throws(() => seedLiveCopy({ source: path.join(root, "nowhere"), live, version: "0.2.0" }), /Install Anexis again/);
  assert.equal(fs.existsSync(live), false);
});

test("reset puts the shipped files back and keeps the edited ones as a backup", () => {
  const { source, live } = scratch();
  seedLiveCopy({ source, live, version: "0.2.0" });
  fs.writeFileSync(path.join(live, "anexis", "core.py"), "broken(\n");
  const result = resetLiveCopy({ source, live, version: "0.2.0" });
  assert.equal(result.action, "updated");
  assert.equal(fs.readFileSync(path.join(live, "anexis", "core.py"), "utf8"), "VERSION = 1\n");
  assert.equal(fs.readFileSync(path.join(result.backup, "anexis", "core.py"), "utf8"), "broken(\n");
});

test("the frame is loaded from the live copy, so it can be edited in place", () => {
  const { source, live } = scratch();
  seedLiveCopy({ source, live, version: "0.2.0" });
  const packed = path.join(source, "desktop", "frame.js");
  fs.writeFileSync(path.join(live, "desktop", "frame.js"), "module.exports = { start() { return 'edited'; } };\n");
  const loaded = loadFrame(live, packed);
  assert.equal(loaded.frame.start(), "edited");
  assert.equal(loaded.problem, "");
});

test("a broken edited frame falls back to the packed one and says why", () => {
  const { source, live } = scratch();
  seedLiveCopy({ source, live, version: "0.2.0" });
  const packed = path.join(source, "desktop", "frame.js");
  fs.writeFileSync(path.join(live, "desktop", "frame.js"), "module.exports = { start( {\n");
  const loaded = loadFrame(live, packed);
  assert.equal(loaded.frame.start(), "shipped");
  assert.equal(loaded.from, packed);
  assert.match(loaded.problem, /frame\.js/);
});

test("running from the source tree loads the frame that is right there", () => {
  const { source } = scratch();
  const packed = path.join(source, "desktop", "frame.js");
  const loaded = loadFrame(source, packed);
  assert.equal(loaded.frame.start(), "shipped");
  assert.equal(loaded.problem, "");
});
