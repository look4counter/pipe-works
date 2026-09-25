const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const sourcePath = path.resolve(
  __dirname,
  "../../src/conductor/web/static/index.js",
);
const source = fs.readFileSync(sourcePath, "utf8");
const browserStartup = source.indexOf(
  'document.addEventListener("DOMContentLoaded"',
);
assert.notEqual(browserStartup, -1, "index.js browser startup hook was found");

const browserHelpers = {};
vm.runInNewContext(source.slice(0, browserStartup), browserHelpers);

test("edit form restores a zero GPU ID from the API gpu_id field", () => {
  const process = browserHelpers.normalizeProcess({
    process_id: "camera-001",
    gpu_id: 0,
  });
  let restored;

  browserHelpers.restoreGpuId(process, (name, value) => {
    restored = { name, value };
  });

  assert.equal(restored.name, "gpuid");
  assert.equal(restored.value, 0);
});

test("edit form restores a nonzero GPU ID", () => {
  const process = browserHelpers.normalizeProcess({
    process_id: "camera-002",
    gpu_id: 3,
  });
  let restored;

  browserHelpers.restoreGpuId(process, (_name, value) => {
    restored = value;
  });

  assert.equal(restored, 3);
});
