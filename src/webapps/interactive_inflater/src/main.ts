import "./style.css";
import { Viewer } from "./viewer";
import { randomFaceColors } from "./colors";
import { fullInflate, type InflateStatus } from "./physics/pipeline";
import { type NetSpec } from "./physics/mesh";

const netSelect = document.getElementById("net-select") as HTMLSelectElement;
const relaxBtn = document.getElementById("relax-btn") as HTMLButtonElement;
const statusStage = document.getElementById("status-stage")!;
const statusSteps = document.getElementById("status-steps")!;
const statusRms = document.getElementById("status-rms")!;
const statusPressure = document.getElementById("status-pressure")!;
const viewerEl = document.getElementById("viewer")!;

const viewer = new Viewer(viewerEl);

interface NetIndexEntry {
  label: string;
  file: string;
}

async function loadNetIndex(): Promise<NetIndexEntry[]> {
  const res = await fetch("nets/index.json");
  if (!res.ok) throw new Error(`Failed to load nets/index.json: ${res.status} ${res.statusText}`);
  return res.json();
}

async function loadNetSpec(file: string): Promise<NetSpec> {
  const res = await fetch(`nets/${file}`);
  if (!res.ok) throw new Error(`Failed to load nets/${file}: ${res.status} ${res.statusText}`);
  return res.json();
}

function setStatus(status: InflateStatus) {
  statusStage.textContent = status.stage === "level0" ? "Level 0 relax" : "Level 1 inflate";
  statusSteps.textContent = String(status.steps);
  if (status.rmsStretchPct !== undefined) statusRms.textContent = status.rmsStretchPct.toFixed(1);
  if (status.pressure !== undefined) statusPressure.textContent = status.pressure.toFixed(2);
}

let running = false;

async function onRelaxClicked() {
  if (running) return;
  running = true;
  relaxBtn.disabled = true;
  statusStage.textContent = "loading...";
  statusSteps.textContent = "--";
  statusRms.textContent = "--";
  statusPressure.textContent = "--";
  try {
    const spec = await loadNetSpec(netSelect.value);
    const result = await fullInflate(spec, { onStatus: setStatus });
    viewer.setMesh(result.faces, result.positions, result.faceOfFine, randomFaceColors(result.baseFaces));
    statusStage.textContent = "done";
    statusRms.textContent = result.rmsStretchPct.toFixed(1);
    statusPressure.textContent = result.pressure.toFixed(2);
  } catch (err) {
    statusStage.textContent = "error";
    console.error(err);
    alert(err instanceof Error ? err.message : String(err));
  } finally {
    running = false;
    relaxBtn.disabled = false;
  }
}

async function init() {
  try {
    const nets = await loadNetIndex();
    for (const net of nets) {
      const option = document.createElement("option");
      option.value = net.file;
      option.textContent = net.label;
      netSelect.appendChild(option);
    }
    relaxBtn.disabled = false;
    relaxBtn.addEventListener("click", onRelaxClicked);
  } catch (err) {
    console.error(err);
    const option = document.createElement("option");
    option.textContent = "Failed to load net list -- see console";
    netSelect.appendChild(option);
    statusStage.textContent = "error";
  }
}

init();
