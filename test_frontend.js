const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const read = name => fs.readFileSync(name, 'utf8');
const userFiles = ['english-learning.html', 'courses.html', 'kids-hub.html', 'kindergarten.html', 'primary.html', 'kids-common.js', 'vocabulary-data.js'];

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
assert(adult.includes('/assets/vocabulary-data.js?v=1.4.0'), 'adult page must load the expanded vocabulary bank');
assert(adult.includes('vocabLimit:60'), 'large vocabulary lists must render in mobile-friendly batches');
assert(adult.includes('id="corpusResults"'), 'adult vocabulary page must expose the large server-side corpus');
assert(adult.includes('/api/content/vocabulary'), 'adult vocabulary page must search the server-side word bank');
assert(adult.includes('/api/content/sentences'), 'adult vocabulary page must search bilingual sentences');
const vocabSandbox = { window: {} };
vocabSandbox.window = vocabSandbox;
vm.createContext(vocabSandbox);
vm.runInContext(read('vocabulary-data.js'), vocabSandbox, { filename: 'vocabulary-data.js' });
const extraVocabulary = vocabSandbox.EXTRA_VOCAB;
assert.equal(extraVocabulary.length, 420, 'expanded vocabulary must add 420 terms');
const categoryCounts = {};
const vocabularyKeys = new Set();
for (const term of extraVocabulary) {
  assert(term.en && term.zh && term.cat && term.ex, 'every vocabulary item needs complete learning content');
  assert(Number.isInteger(term.lv) && term.lv >= 0 && term.lv <= 3, `${term.en} has an invalid level`);
  categoryCounts[term.cat] = (categoryCounts[term.cat] || 0) + 1;
  const key = `${term.cat}|${term.en.toLowerCase()}`;
  assert(!vocabularyKeys.has(key), `duplicate expanded vocabulary item: ${key}`);
  vocabularyKeys.add(key);
}
for (const category of ['daily', 'business', 'engineering', 'it', 'medical', 'finance']) {
  assert.equal(categoryCounts[category], 70, `${category} must add 70 terms`);
}
const baseVocabularyBlock = adult.slice(adult.indexOf('const VOCAB = ['), adult.indexOf('Array.prototype.push.apply'));
const baseVocabulary = [...baseVocabularyBlock.matchAll(/\{en:(["'])(.*?)\1,ph:[\s\S]*?cat:(["'])(.*?)\3,ex:/g)]
  .map(match => ({ en: match[2], cat: match[4] }));
assert.equal(baseVocabulary.length + extraVocabulary.length, 516, 'the complete vocabulary bank must contain 516 terms');
for (const term of baseVocabulary) {
  const key = `${term.cat}|${term.en.toLowerCase()}`;
  assert(!vocabularyKeys.has(key), `expanded vocabulary duplicates a built-in item: ${key}`);
  vocabularyKeys.add(key);
}
assert(read('kindergarten.html').includes('playFeaturedCartoon(this)'));
assert(read('primary.html').includes('playCurrent(this)'));

const curriculumUnits = new Set();
for (const stage of ['kindergarten','primary','junior','senior','university','general']) {
  const data = JSON.parse(read(`content/curriculum/${stage}.json`));
  assert.equal(data.id, stage);
  assert(data.units.length >= 12, `${stage} needs substantive course units`);
  const bands = new Set(data.bands.map(band => String(band.id)));
  for (const unit of data.units) {
    assert(!curriculumUnits.has(unit.id), `duplicate unit: ${unit.id}`);
    curriculumUnits.add(unit.id);
    assert(bands.has(String(unit.band)), `${unit.id}: invalid grade`);
    assert(unit.goal && unit.knowledge.length >= 3 && unit.vocabulary.length >= 5 && unit.dialogue.length >= 3, `${unit.id}: incomplete lesson`);
    assert(unit.reading.en && unit.reading.zh && unit.writing.prompt && unit.writing.sample && unit.writing.checklist.length, `${unit.id}: missing reading or expression task`);
    const questionIds = new Set();
    assert(unit.questions.length >= 4, `${unit.id}: missing practice`);
    for (const question of unit.questions) {
      assert(!questionIds.has(question.id), `${unit.id}: duplicate question`);
      questionIds.add(question.id);
      const accepted = Array.isArray(question.answer) ? question.answer : [question.answer];
      assert(accepted.length && accepted.every(answer => typeof answer === 'string' && answer.trim()), `${unit.id}: missing answer`);
      assert(question.explanation && question.prompt, `${unit.id}: missing feedback`);
      if (question.type === 'choice') {
        assert.equal(new Set(question.options).size, question.options.length, `${unit.id}: duplicate choices`);
        assert(accepted.every(answer => question.options.includes(answer)), `${unit.id}: answer absent from choices`);
      }
    }
  }
}
assert.equal(curriculumUnits.size, 72);

console.log('frontend checks passed');
