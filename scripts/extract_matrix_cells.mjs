#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const body = fs.readFileSync(
  path.join(ROOT, 'notes/synthesis/agent-skill-architecture-survey-matrix.md'),
  'utf8'
);
const cells = new Set();
for (const line of body.split('\n')) {
  if (!line.startsWith('| **')) continue;
  if (line.includes(':---')) continue;
  const parts = line.split('|').map((s) => s.trim()).filter(Boolean);
  if (parts.length < 9) continue;
  parts.slice(1).forEach((c) => cells.add(c));
}
fs.writeFileSync(
  path.join(ROOT, 'config/matrix-cells-unique.json'),
  JSON.stringify([...cells].sort(), null, 2)
);
console.log('unique cells:', cells.size);
