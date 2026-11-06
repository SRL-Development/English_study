const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const read = name => fs.readFileSync(name, 'utf8');
const userFiles = ['english-learning.html', 'kids-hub.html', 'kindergarten.html', 'primary.html', 'kids-common.js'];

for (const file of userFiles) {
  const source = read(file);
  assert(!source.includes('?.'), `${file} must stay compatible with older iPhone Safari (optional chaining)`);
  assert(!source.includes('??'), `${file} must stay compatible with older iPhone Safari (nullish coalescing)`);
  assert(!source.includes('Object.fromEntries'), `${file} must not require Object.fromEntries`);
  if (file.endsWith('.html')) {
    const scripts = [...source.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
    scripts.forEach((match, index) => new vm.Script(match[1], { filename: `${file}#${index + 1}` }));
  }
}

const storage = new Map();
const sandbox = {
  window: {},
  localStorage: {
    getItem: key => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key),
  },
  document: { getElementById: () => null, body: { appendChild() {} }, createElement: () => ({ classList: { add() {}, remove() {} } }) },
  location: { href: '', replace() {} },
  fetch: async () => ({ status: 200, json: async () => ({}) }),
  AbortController,
  setTimeout,
  clearTimeout,
  Date,
  JSON,
  Math,
  Number,
  String,
  Array,
  Object,
  Promise,
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(read('kids-common.js'), sandbox, { filename: 'kids-common.js' });

const progress = sandbox.KidsAPI.normalizeProgress({});
const payload = { question: 'Choose cat.', answer: 'cat', options: ['cat', 'dog'] };
sandbox.KidsAPI.recordAttempt(progress, 'primary', 'p1', payload, false, 'dog');
assert.equal(sandbox.KidsAPI.wrongEntries(progress, 'primary').length, 1);
for (let i = 0; i < 9; i += 1) sandbox.KidsAPI.recordAttempt(progress, 'primary', 'p1', payload, true, 'cat');
assert.equal(sandbox.KidsAPI.wrongEntries(progress, 'primary')[0].streak, 9);
const result = sandbox.KidsAPI.recordAttempt(progress, 'primary', 'p1', payload, true, 'cat');
assert.equal(result.removed, true);
assert.equal(sandbox.KidsAPI.wrongEntries(progress, 'primary').length, 0);

const adult = read('english-learning.html');
assert(adult.includes('class="heat-grid"'), 'heat map must use the Safari-safe grid renderer');
assert(adult.includes('id="gramInput"'), 'grammar practice must use inline blank input');
assert(adult.includes('recordAdultAttempt'), 'adult mistakes must be persisted');
assert((adult.match(/\{q:'/g) || []).length >= 20, 'grammar bank must contain at least 20 questions');
assert(read('kindergarten.html').includes('playFeaturedCartoon(this)'));
assert(read('primary.html').includes('playCurrent(this)'));

console.log('frontend checks passed');
