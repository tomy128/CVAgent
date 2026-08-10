import assert from "node:assert/strict";
import test from "node:test";

import { initializeConfigDisclosures } from "../src/resume_agent/web/static/config-disclosure.mjs";

class FakeTrigger {
  constructor(panelId) {
    this.attributes = new Map([
      ["aria-controls", panelId],
      ["aria-expanded", "false"],
    ]);
    this.listeners = new Map();
  }

  getAttribute(name) { return this.attributes.get(name); }
  setAttribute(name, value) { this.attributes.set(name, value); }
  addEventListener(type, listener) { this.listeners.set(type, listener); }
  click() { this.listeners.get("click")(); }
}

function fixture() {
  const triggers = [new FakeTrigger("llm-panel"), new FakeTrigger("embedding-panel")];
  const panels = new Map([
    ["llm-panel", { hidden: true }],
    ["embedding-panel", { hidden: true }],
  ]);
  return {
    triggers,
    panels,
    root: {
      querySelectorAll: () => triggers,
      getElementById: (id) => panels.get(id),
    },
  };
}

test("initializes both model panels expanded on every fresh load", () => {
  const { root, triggers, panels } = fixture();

  initializeConfigDisclosures(root);

  assert.deepEqual(triggers.map((trigger) => trigger.getAttribute("aria-expanded")), ["true", "true"]);
  assert.deepEqual([...panels.values()].map((panel) => panel.hidden), [false, false]);
});

test("toggles LLM and Embedding independently with synchronized state", () => {
  const { root, triggers, panels } = fixture();
  initializeConfigDisclosures(root);

  triggers[0].click();
  assert.equal(triggers[0].getAttribute("aria-expanded"), "false");
  assert.equal(panels.get("llm-panel").hidden, true);
  assert.equal(triggers[1].getAttribute("aria-expanded"), "true");
  assert.equal(panels.get("embedding-panel").hidden, false);

  triggers[1].click();
  triggers[0].click();
  assert.equal(triggers[0].getAttribute("aria-expanded"), "true");
  assert.equal(panels.get("llm-panel").hidden, false);
  assert.equal(triggers[1].getAttribute("aria-expanded"), "false");
  assert.equal(panels.get("embedding-panel").hidden, true);
});
