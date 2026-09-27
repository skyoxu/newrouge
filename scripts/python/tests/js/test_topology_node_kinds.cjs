'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../../..');
const controls = {};
const context = {
  document: {getElementById(id) {
    return controls[id] ||= {value: '', addEventListener() {}};
  }},
  window: {location: {search: ''}},
  URLSearchParams,
  fetch: async () => ({ok: true, json: async () => ({})}),
};
vm.createContext(context);
let source = fs.readFileSync(path.join(root, 'scripts/python/project_health_topology.js'), 'utf8');
// Avoid the automatic initial HTTP load while exercising real UI functions.
source = source.replace(/^load\(\)\.catch.*$/m, '');
vm.runInContext(source, context);
const requirements = JSON.parse(fs.readFileSync(path.join(root,
  'docs/planning/semantic-topology/semantic-requirements.v1.json'), 'utf8')).requirements;
context.input = {nodes: {requirements}, edges: [], fresh: true};
vm.runInContext('topology = input', context);
controls['filter-kind'].value = 'requirement';
const nodes = context.nodeRows(context.input);
assert.equal(nodes.filter(context.matches).length, requirements.length);
assert.ok(requirements.length > 0);
assert.equal(nodes[0].kind, requirements[0].kind);
assert.equal(nodes[0].node_kind, 'requirement');
const related = context.relatedNodes(nodes[0]);
assert.ok(related.some(x => x.kind === 'source_block'));
context.input.edges = [{source_type: 'requirement', source_id: nodes[0].requirement_id,
  target_type: 'task', target_id: '1', relation: 'implemented_by'}];
assert.ok(context.relatedNodes(nodes[0]).some(x => x.kind === 'task' && x.id === '1'));
controls['filter-state'].value = 'orphan';
assert.equal(nodes.filter(context.matches).length, 0);
assert.equal(context.matches({...nodes[0], sink_resolved: false}), true);
controls['filter-state'].value = '';
controls['filter-kind'].value = 'capability';
assert.equal(nodes.filter(context.matches).length, 0);
assert.equal(context.matches(context.nodeRows({nodes: {capabilities: [{capability_id: 'CAP-1'}]}})[0]), true);
console.log('Topology node kind regression passed: real requirements, semantic kinds, filters and related links.');
