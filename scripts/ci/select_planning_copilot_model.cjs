"use strict";

// Discover a selectable model before the bounded planning chain creates a run.
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { createRequire } = require("node:module");

const PREFERRED = ["gpt-6-luna", "mai-code-1.1-flash", "gpt-5.4-mini", "gpt-5-mini",
  "claude-haiku-4.5", "claude-sonnet-4.6", "gpt-5.4"];

function selectModel(models, requested = "") {
  if (!Array.isArray(models)) throw new Error("Copilot model inventory must be an array");
  const available = new Set();
  const seen = new Set();
  for (const model of models) {
    if (!model || typeof model.id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._-]+$/.test(model.id)) {
      throw new Error("Copilot model inventory contains an invalid model ID");
    }
    if (seen.has(model.id)) throw new Error("Copilot model inventory contains duplicate model IDs");
    seen.add(model.id);
    if (model.id.toLowerCase() === "auto") continue;
    if (model.policy && model.policy.state !== "enabled") continue;
    available.add(model.id);
  }
  requested = requested.trim();
  if (requested && requested.toLowerCase() !== "auto") {
    if (!available.has(requested)) throw new Error("Requested planning model is unavailable: " + requested);
    return requested;
  }
  const selected = PREFERRED.find(model => available.has(model)) || [...available].sort()[0];
  if (!selected) throw new Error("No planning model is enabled; configure SC_PLANNING_COPILOT_MODEL");
  return selected;
}

async function discover(sdk, options) {
  const client = new sdk.CopilotClient(options);
  try {
    await client.start();
    return await client.listModels();
  } finally {
    await client.stop();
  }
}

async function main() {
  const sdkRoot = process.env.SC_PLANNING_COPILOT_SDK;
  const cliPath = process.env.SC_PLANNING_COPILOT_CLI;
  const envFile = process.env.GITHUB_ENV;
  if (!sdkRoot || !cliPath || !envFile) throw new Error("SDK, CLI and GitHub environment-file paths are required");
  const sdk = createRequire(path.join(path.resolve(sdkRoot), "package.json"))("@github/copilot-sdk");
  const runtime = fs.mkdtempSync(path.join(os.tmpdir(), "planning-model-discovery-"));
  try {
    const models = await discover(sdk, {
      connection: sdk.RuntimeConnection.forStdio({ path: cliPath }),
      gitHubToken: process.env.COPILOT_GITHUB_TOKEN || process.env.GITHUB_TOKEN,
      useLoggedInUser: false, baseDirectory: runtime, logLevel: "error",
    });
    const evidence = path.resolve("logs/ci/planning-model-discovery");
    fs.mkdirSync(evidence, { recursive: true });
    const record = {
      schema_version: "newrouge.planning-model-selection.v1", status: "blocked",
      model_inventory: models.map(model => ({ id: model.id, policy: model.policy?.state || "available" })),
      inference_invocations: 0,
    };
    let selected;
    try {
      selected = selectModel(models, process.env.SC_COPILOT_MODEL || "");
      record.status = "selected";
      record.selected_model = selected;
    } catch (error) {
      record.reason = error.message;
      throw error;
    } finally {
      fs.writeFileSync(path.join(evidence, "selection.json"), JSON.stringify(record, null, 2) + "\n");
    }
    fs.appendFileSync(envFile, "SC_COPILOT_MODEL=" + selected + "\n");
    process.stdout.write("PLANNING_MODEL_SELECTION model=" + selected + " inference_invocations=0\n");
  } finally {
    fs.rmSync(runtime, { recursive: true, force: true });
  }
}

module.exports = { selectModel, discover };
if (require.main === module) main().catch(error => {
  process.stderr.write("PLANNING_MODEL_SELECTION blocked: " + error.message + "\n");
  process.exitCode = 1;
});
