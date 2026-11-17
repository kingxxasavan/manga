// The live copy: the folder of plain files the app actually runs from.
//
// The installer ships the app's files read only inside the install folder.
// On first launch they are copied to a folder the owner (and Claude) can edit.
// From then on the app runs from that copy, which is why changing a file
// changes the app with no new installer.
//
// This file uses only Node, no Electron, so it can be tested on its own.

const fs = require("node:fs");
const path = require("node:path");

const MARKER = ".anexis-version";
const SKIP = new Set(["__pycache__", "node_modules", ".git", ".venv", "dist", "stage"]);

function copyTree(from, to) {
  fs.cpSync(from, to, {
    recursive: true,
    filter: (src) => !SKIP.has(path.basename(src)) && !src.endsWith(".pyc"),
  });
}

function seededVersion(live) {
  try {
    return fs.readFileSync(path.join(live, MARKER), "utf8").trim();
  } catch {
    return "";
  }
}

/**
 * Makes sure `live` holds the app's files for `version`.
 *
 *   seeded   there was no live copy, the shipped files were copied in
 *   kept     the live copy is from this version, nothing was touched
 *   updated  the live copy was from another version: it was moved aside,
 *            whole, to `backup`, and the shipped files were copied in
 *
 * A live copy is never deleted and never merged over, so edits made to it
 * are always still on disk somewhere.
 */
function seedLiveCopy({ source, live, version, now = new Date() }) {
  if (!fs.existsSync(path.join(source, "anexis"))) {
    throw new Error(`The app's own files are missing from ${source}. Install Anexis again.`);
  }
  const had = seededVersion(live);
  let action = "seeded", backup = "";
  if (fs.existsSync(live)) {
    if (had === version) return { action: "kept", live, backup };
    const stamp = now.toISOString().replace(/[-:T]/g, "").slice(0, 14);
    backup = path.join(path.dirname(live), `app-backup-${had || "unknown"}-${stamp}`);
    fs.renameSync(live, backup);
    action = "updated";
  }
  fs.mkdirSync(path.dirname(live), { recursive: true });
  const staging = `${live}.incoming`;
  fs.rmSync(staging, { recursive: true, force: true });
  copyTree(source, staging);
  fs.writeFileSync(path.join(staging, MARKER), `${version}\n`);
  fs.renameSync(staging, live);  // appears all at once, never half copied
  return { action, live, backup };
}

/** Puts the shipped files back, keeping the current live copy as a backup. */
function resetLiveCopy({ source, live, version, now = new Date() }) {
  try {
    fs.writeFileSync(path.join(live, MARKER), "reset\n");
  } catch { /* no live copy yet, seeding makes one */ }
  return seedLiveCopy({ source, live, version, now });
}

/**
 * Loads the frame from the live copy, so even the window code can be edited
 * in place. If that copy is broken the one packed inside the app is used, so
 * a bad edit can never stop the app from opening.
 */
function loadFrame(live, packed) {
  const edited = path.join(live, "desktop", "frame.js");
  if (path.resolve(edited) !== path.resolve(packed) && fs.existsSync(edited)) {
    try {
      return { frame: require(edited), from: edited, problem: "" };
    } catch (error) {
      return { frame: require(packed), from: packed, problem: `${edited}: ${error.message}` };
    }
  }
  return { frame: require(packed), from: packed, problem: "" };
}

module.exports = { seedLiveCopy, resetLiveCopy, loadFrame, seededVersion, MARKER };
