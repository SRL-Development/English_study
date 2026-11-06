import fs from 'node:fs';
import path from 'node:path';
import { pipeline } from 'node:stream/promises';
import { fileURLToPath } from 'node:url';
import { parse } from 'csv-parse';
import initSqlJs from 'sql.js';
import unbzip2 from 'unbzip2-stream';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..');
const cache = path.join(here, '.cache');
const outputDir = path.join(root, 'content');
const output = path.join(outputDir, 'content.db');
const WORD_LIMIT = Number(process.env.WORD_LIMIT || 30000);
const SENTENCE_LIMIT = Number(process.env.SENTENCE_LIMIT || 30000);

const SOURCES = {
  dictionary: 'https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv',
  english: 'https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2',
  chinese: 'https://downloads.tatoeba.org/exports/per_language/cmn/cmn_sentences.tsv.bz2',
  links: 'https://downloads.tatoeba.org/exports/per_language/eng/eng-cmn_links.tsv.bz2'
};

fs.mkdirSync(cache, { recursive: true });
fs.mkdirSync(outputDir, { recursive: true });

async function download(url, target) {
  if (fs.existsSync(target) && fs.statSync(target).size > 0) return;
  console.log('Downloading', url);
  const response = await fetch(url, { redirect: 'follow' });
  if (!response.ok || !response.body) throw new Error(`Download failed: ${response.status} ${url}`);
  await pipeline(response.body, fs.createWriteStream(target));
}

async function decompress(source, target) {
  if (fs.existsSync(target) && fs.statSync(target).size > 0) return;
  console.log('Decompressing', path.basename(source));
  await pipeline(fs.createReadStream(source), unbzip2(), fs.createWriteStream(target));
}

function numericRank(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 999999;
}

function cleanText(value, maxLength) {
  return String(value || '').replace(/\\n/g, '；').replace(/\s+/g, ' ').trim().slice(0, maxLength);
}

function normalizeTags(raw) {
  const values = new Set(String(raw || '').toLowerCase().split(/\s+/).filter(Boolean));
  const result = [];
  const mapping = [
    ['ky', '考研'], ['cet6', '六级'], ['cet4', '四级'], ['gre', 'GRE'],
    ['toefl', '托福'], ['ielts', '雅思'], ['sat', 'SAT'], ['gk', '高考'], ['zk', '中考']
  ];
  mapping.forEach(([key, label]) => { if (values.has(key)) result.push(label); });
  return result;
}

function wordLevel(tags, rank) {
  if (tags.some(tag => ['GRE', '托福', '雅思', 'SAT'].includes(tag))) return 3;
  if (tags.some(tag => ['考研', '六级'].includes(tag))) return 2;
  if (tags.some(tag => ['四级', '高考', '中考'].includes(tag))) return 1;
  if (rank <= 5000) return 1;
  if (rank <= 14000) return 2;
  return 3;
}

function wordScore(tags, rank, word) {
  const weights = { GRE: 1300, 托福: 1250, 雅思: 1250, 考研: 1200, 六级: 1050, SAT: 1000, 四级: 850, 高考: 750, 中考: 650 };
  let score = Math.max(0, ...tags.map(tag => weights[tag] || 0));
  if (rank < 999999) score += Math.max(0, 700 - Math.floor(rank / 35));
  if (/^[A-Za-z][A-Za-z -]{1,38}$/.test(word)) score += 80;
  return score;
}

async function loadWords() {
  const source = path.join(cache, 'ecdict.csv');
  await download(SOURCES.dictionary, source);
  const candidates = [];
  const seen = new Set();
  const parser = fs.createReadStream(source).pipe(parse({ columns: true, bom: true, relax_quotes: true, relax_column_count: true }));
  for await (const row of parser) {
    const word = cleanText(row.word, 48);
    const key = word.toLowerCase();
    const translation = cleanText(row.translation, 700);
    if (!word || !translation || seen.has(key) || !/^[A-Za-z][A-Za-z '-]{1,46}$/.test(word)) continue;
    if (word.split(/\s+/).length > 5) continue;
    const tags = normalizeTags(row.tag);
    const rank = Math.min(numericRank(row.bnc), numericRank(row.frq));
    const level = wordLevel(tags, rank);
    candidates.push({
      word,
      phonetic: cleanText(row.phonetic, 100),
      translation,
      definition: cleanText(row.definition, 900),
      pos: cleanText(row.pos, 120),
      tags: tags.join(','),
      level,
      rank,
      score: wordScore(tags, rank, word)
    });
    seen.add(key);
  }
  candidates.sort((a, b) => b.score - a.score || a.rank - b.rank || a.word.localeCompare(b.word));
  const selected = candidates.slice(0, WORD_LIMIT);
  selected.sort((a, b) => a.word.localeCompare(b.word));
  console.log(`Selected ${selected.length} vocabulary items from ${candidates.length} candidates`);
  return selected;
}

async function readSentenceMap(file) {
  const result = new Map();
  const content = fs.readFileSync(file, 'utf8');
  content.split(/\r?\n/).forEach(line => {
    if (!line) return;
    const first = line.indexOf('\t');
    const second = line.indexOf('\t', first + 1);
    const id = Number(line.slice(0, first));
    const text = line.slice(second >= 0 ? second + 1 : first + 1).trim();
    if (id && text) result.set(id, text);
  });
  return result;
}

function sentenceLevel(english, advancedWords) {
  const tokens = english.toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) || [];
  const advanced = tokens.reduce((count, token) => count + (advancedWords.has(token) ? 1 : 0), 0);
  if (tokens.length <= 9 && advanced === 0) return 1;
  if (tokens.length <= 15 && advanced === 0) return 2;
  return 3;
}

async function loadSentences(words) {
  const compressed = {};
  const expanded = {};
  for (const key of ['english', 'chinese', 'links']) {
    compressed[key] = path.join(cache, `${key}.tsv.bz2`);
    expanded[key] = path.join(cache, `${key}.tsv`);
    await download(SOURCES[key], compressed[key]);
    await decompress(compressed[key], expanded[key]);
  }
  const english = await readSentenceMap(expanded.english);
  const chinese = await readSentenceMap(expanded.chinese);
  const advancedWords = new Set(
    words
      .filter(item => item.level === 3 && item.rank > 12000 && item.word.length >= 6 && !item.word.includes(' '))
      .map(item => item.word.toLowerCase())
  );
  const buckets = { 1: [], 2: [], 3: [] };
  const seen = new Set();
  const links = fs.readFileSync(expanded.links, 'utf8').split(/\r?\n/);
  for (const line of links) {
    if (!line) continue;
    const [englishIdRaw, chineseIdRaw] = line.split('\t');
    const sourceId = Number(englishIdRaw);
    const chineseId = Number(chineseIdRaw);
    const en = cleanText(english.get(sourceId), 240);
    const zh = cleanText(chinese.get(chineseId), 180);
    const key = en.toLowerCase();
    if (!en || !zh || seen.has(key) || en.length < 12 || en.length > 220 || zh.length < 3) continue;
    if (!/[A-Za-z]/.test(en) || !/[\u3400-\u9fff]/.test(zh) || /https?:\/\//i.test(en)) continue;
    const level = sentenceLevel(en, advancedWords);
    buckets[level].push({ english: en, chinese: zh, level, sourceId });
    seen.add(key);
  }
  const selected = [];
  const perLevel = Math.floor(SENTENCE_LIMIT / 3);
  [1, 2, 3].forEach(level => selected.push(...buckets[level].slice(0, perLevel)));
  if (selected.length < SENTENCE_LIMIT) {
    const selectedIds = new Set(selected.map(item => item.sourceId));
    [3, 2, 1].forEach(level => {
      for (const item of buckets[level]) {
        if (selected.length >= SENTENCE_LIMIT) break;
        if (!selectedIds.has(item.sourceId)) {
          selected.push(item);
          selectedIds.add(item.sourceId);
        }
      }
    });
  }
  console.log(`Selected ${selected.length} bilingual sentences (${selected.filter(x => x.level === 1).length}/${selected.filter(x => x.level === 2).length}/${selected.filter(x => x.level === 3).length})`);
  return selected;
}

async function buildDatabase(words, sentences) {
  const SQL = await initSqlJs({ locateFile: file => path.join(here, 'node_modules', 'sql.js', 'dist', file) });
  const db = new SQL.Database();
  db.run(`
    PRAGMA journal_mode=OFF;
    CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE vocabulary (
      id INTEGER PRIMARY KEY, word TEXT NOT NULL UNIQUE COLLATE NOCASE, phonetic TEXT,
      translation TEXT NOT NULL, definition TEXT, pos TEXT, tags TEXT, level INTEGER NOT NULL,
      frequency_rank INTEGER
    );
    CREATE INDEX idx_vocabulary_level ON vocabulary(level);
    CREATE INDEX idx_vocabulary_tags ON vocabulary(tags);
    CREATE TABLE sentences (
      id INTEGER PRIMARY KEY, english TEXT NOT NULL, chinese TEXT NOT NULL,
      level INTEGER NOT NULL, source_id INTEGER NOT NULL
    );
    CREATE INDEX idx_sentences_level ON sentences(level);
  `);
  db.run('BEGIN');
  const wordInsert = db.prepare('INSERT INTO vocabulary(word,phonetic,translation,definition,pos,tags,level,frequency_rank) VALUES (?,?,?,?,?,?,?,?)');
  words.forEach(item => wordInsert.run([item.word, item.phonetic, item.translation, item.definition, item.pos, item.tags, item.level, item.rank]));
  wordInsert.free();
  const sentenceInsert = db.prepare('INSERT INTO sentences(english,chinese,level,source_id) VALUES (?,?,?,?)');
  sentences.forEach(item => sentenceInsert.run([item.english, item.chinese, item.level, item.sourceId]));
  sentenceInsert.free();
  const metadata = [
    ['version', '2026.11'], ['vocabulary_count', String(words.length)],
    ['sentence_count', String(sentences.length)], ['dictionary_source', 'ECDICT'],
    ['sentence_source', 'Tatoeba'], ['sentence_license', 'CC BY 2.0 FR']
  ];
  const metadataInsert = db.prepare('INSERT INTO metadata(key,value) VALUES (?,?)');
  metadata.forEach(item => metadataInsert.run(item));
  metadataInsert.free();
  db.run('COMMIT');
  db.run('ANALYZE');
  fs.writeFileSync(output, Buffer.from(db.export()));
  db.close();
  console.log(`Wrote ${output} (${(fs.statSync(output).size / 1024 / 1024).toFixed(1)} MiB)`);
}

const words = await loadWords();
const sentences = await loadSentences(words);
await buildDatabase(words, sentences);
