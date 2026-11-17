// The first thing the desktop app runs. It does two small jobs and hands over:
//   1. make sure the live copy of the app's files is in place (see seed.js)
//   2. load frame.js from that live copy and start it
// Everything interesting is in frame.js, which can be edited in place.

const { app, dialog } = require("electron");
const path = require("node:path");
const { loadFrame, seedLiveCopy } = require("./seed.js");

function paths() {
  if (!app.isPackaged) {
    // Running from the source tree (npm start): the repo is the live copy.
    return { live: path.resolve(__dirname, ".."), runtime: "", source: "" };
  }
  const data = path.join(process.env.LOCALAPPDATA || app.getPath("userData"), "Anexis");
  return {
    live: path.join(data, "app"),
    runtime: path.join(process.resourcesPath, "runtime"),
    source: path.join(process.resourcesPath, "source"),
  };
}

function main() {
  const where = paths();
  let seeded = { action: "kept", live: where.live, backup: "" };
  if (where.source) {
    try {
      seeded = seedLiveCopy({ source: where.source, live: where.live, version: app.getVersion() });
    } catch (error) {
      dialog.showErrorBox("Anexis could not set up its files", `${error.message}\n\nFolder: ${where.live}`);
      app.exit(1);
      return;
    }
  }
  const packed = path.join(__dirname, "frame.js");
  const { frame, problem } = loadFrame(where.live, packed);
  const context = { ...where, seeded, version: app.getVersion(), frameProblem: problem, packed };
  try {
    frame.start(context);
  } catch (error) {
    // The edited frame loaded but fell over while starting. Use the packed one.
    require(packed).start({ ...context, frameProblem: `${error.message}` });
  }
}

main();
