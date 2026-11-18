// The one thing the deck may ask of the window: open the Canvas sign in.
// Nothing else from the desktop is reachable from the page.

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("anexisFrame", {
  canvasSignIn: (url) => ipcRenderer.invoke("canvas-sign-in", String(url || "")),
});
