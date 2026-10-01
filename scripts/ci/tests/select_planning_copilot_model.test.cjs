"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const { selectModel, discover } = require("../select_planning_copilot_model.cjs");
const enabled = id => ({ id, policy: { state: "enabled" } });

test("discovery never creates a model session or sends a prompt", async () => {
  const calls = [];
  class Client {
    async start() { calls.push("start"); }
    async listModels() { calls.push("list"); return [enabled("gpt-5-mini")]; }
    async stop() { calls.push("stop"); }
    createSession() { assert.fail("discovery must not invoke inference"); }
  }
  assert.deepEqual(await discover({ CopilotClient: Client }, {}), [enabled("gpt-5-mini")]);
  assert.deepEqual(calls, ["start", "list", "stop"]);
});

test("discovery stops its runtime after inventory failure", async () => {
  let stopped = false;
  class Client {
    async start() {}
    async listModels() { throw new Error("inventory unavailable"); }
    async stop() { stopped = true; }
  }
  await assert.rejects(discover({ CopilotClient: Client }, {}), /inventory unavailable/);
  assert.equal(stopped, true);
});

test("default selection skips unavailable actual-execution labels and is order independent", () => {
  const models = [enabled("claude-sonnet-4.6"), enabled("gpt-5-mini")];
  assert.equal(selectModel(models), "gpt-5-mini");
  assert.equal(selectModel(models.reverse(), "auto"), "gpt-5-mini");
});

test("disabled and unconfigured models cannot be selected", () => {
  const models = [{ id: "gpt-6-luna", policy: { state: "unconfigured" } },
    { id: "mai-code-1.1-flash", policy: { state: "disabled" } }, enabled("gpt-5-mini")];
  assert.equal(selectModel(models), "gpt-5-mini");
  assert.throws(() => selectModel(models, "gpt-6-luna"), /unavailable/);
});

test("explicit unavailable choice fails before creating planning runs", () => {
  assert.throws(() => selectModel([enabled("gpt-5-mini")], "gpt-6-luna"), /unavailable/);
  assert.equal(selectModel([enabled("custom-allowed")], "custom-allowed"), "custom-allowed");
});

test("empty inventory fails without auto fallback and new enabled models remain usable", () => {
  assert.throws(() => selectModel([enabled("auto")]), /No planning model/);
  assert.equal(selectModel([enabled("new-model-z"), enabled("new-model-a")]), "new-model-a");
});

test("invalid and duplicate model IDs fail closed", () => {
  assert.throws(() => selectModel([enabled("gpt-5-mini\nTOKEN=hidden")]), /invalid model ID/);
  assert.throws(() => selectModel([enabled("gpt-5-mini"), enabled("gpt-5-mini")]), /duplicate/);
  assert.throws(() => selectModel({}), /must be an array/);
});
