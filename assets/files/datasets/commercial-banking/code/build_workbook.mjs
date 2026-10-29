#!/usr/bin/env node
/**
 * Research workbook for version 0.1.0 dataset.
 *
 * Run with the bundled runtime:
 *   "$CODEX_PRIMARY_RUNTIME_NODE" code/build_workbook.mjs
 * Optional: --release-root PATH --output PATH --qa-dir PATH --render-scope publication
 *
 * Requires @oai/artifact-tool. In the bundled runtime, this script copies itself
 * into a temporary working directory with a runtime node_modules symlink.
 * It does not alter the CSV release, access the network or publish anything.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import assert from 'node:assert/strict';

const scriptPath = fileURLToPath(import.meta.url);
const args = Object.fromEntries(process.argv.slice(2).reduce((out, x, i, all) => {
  if (x.startsWith('--')) out.push([x.slice(2), all[i + 1]]);
  return out;
}, []));
const releaseRoot = path.resolve(args['release-root'] || path.join(path.dirname(scriptPath), '..'));
const outputPath = path.resolve(args.output || path.join(releaseRoot, '..', 'Czechoslovak_Commercial_Banking_1919_1937.xlsx'));
const outputDir = path.dirname(outputPath);
const qaDir = path.resolve(args['qa-dir'] || path.join(outputDir, 'qa', 'workbook'));

if (process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES && process.env.BANKING_WORKBOOK_STAGE !== 'temporary') {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'banking_workbook_'));
  await fs.symlink(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, path.join(temp, 'node_modules'), 'dir');
  await fs.copyFile(scriptPath, path.join(temp, 'build_workbook.mjs'));
  const result = spawnSync(process.execPath, [path.join(temp, 'build_workbook.mjs'), '--release-root', releaseRoot,
    '--output', outputPath, '--qa-dir', qaDir, '--render-scope', args['render-scope'] || 'all'], {
    cwd: temp, stdio: 'inherit', env: { ...process.env, BANKING_WORKBOOK_STAGE: 'temporary' },
  });
  if (result.error) throw result.error;
  process.exit(result.status ?? 1);
}

const { Workbook, SpreadsheetFile, FileBlob } = await import('@oai/artifact-tool');
const started = Date.now();
const C = { paper: '#F4F0E7', ink: '#162B36', burgundy: '#7A2E34', teal: '#337E7B', muted: '#67757B',
  rule: '#D1D6D6', light: '#F8FAFA', white: '#FFFFFF', amber: '#FFF0CD' };
const FONT = 'Arial';
const NUM = '#,##0.000';
const INT = '0';
const RATIO = '0.00';
const firstDataRow = 8;
const sheets = ['Explore', 'Read me', 'Annual assets', 'Annual funding', 'Annual income', 'Annual ratios',
  'Bank assets', 'Bank funding', 'Bank income', 'Bank ratios', 'Monetary context', 'Institutions',
  'Dictionary', 'Source notes'];
const wb = Workbook.create();
const ws = Object.fromEntries(sheets.map(name => [name, wb.worksheets.add(name)]));
const inputCells = [];
const formulaChecks = [];
const tableMaps = {};
const renderPlan = [];
const csvFiles = [];
const chartObjects = [];
const columnWidths = {};
const declaredTypes = new Map();

function col(n) {
  let s = '';
  while (n > 0) { n--; s = String.fromCharCode(65 + n % 26) + s; n = Math.floor(n / 26); }
  return s;
}
function quote(name) { return `'${name.replaceAll("'", "''")}'`; }
function escapeLiteral(s) { return String(s).replaceAll('"', '""'); }
function nice(s) { return s.replaceAll('_', ' '); }
function money(v) { return typeof v === 'number'; }
function equalValue(actual, expected, label, tolerance = 1e-8) {
  if (expected === null || expected === undefined || expected === '') {
    assert.ok(actual === null || actual === undefined || actual === '', `${label}: expected blank, got ${actual}`);
  } else if (typeof expected === 'number') {
    assert.equal(typeof actual, 'number', `${label}: numeric cell required, got ${typeof actual}`);
    assert.ok(Math.abs(actual - expected) <= tolerance * Math.max(1, Math.abs(expected)),
      `${label}: ${actual} != ${expected}`);
  } else assert.equal(actual, expected, label);
}

async function readCsv(relative) {
  const csvText = await fs.readFile(path.join(releaseRoot, relative), 'utf8');
  const imported = await Workbook.fromCSV(csvText, { sheetName: 'Import' });
  const matrix = imported.worksheets.getItemAt(0).getUsedRange().values;
  const headers = matrix[0].map(String);
  const raw = matrix.slice(1).filter(r => r.some(v => v !== null && v !== undefined && v !== ''));
  const dataset = path.basename(relative, '.csv');
  const numeric = new Set(headers.filter((h, j) => {
    const declared = declaredTypes.get(`${dataset}:${h}`);
    if (declared) return declared === 'integer' || declared === 'number';
    if (/(?:^|_)id(?:_|$)|(?:url|name|note|edition|description|flag|unit|field|variable|file|table|label|formula|type|key|encoding|date|cell|locator)/i.test(h)) return false;
    const values = raw.map(r => r[j]).filter(v => v !== '' && v !== null && v !== undefined);
    return values.length && values.every(v => /^-?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(String(v)));
  }));
  const rows = raw.map(row => headers.map((h, j) => {
    const v = row[j];
    if (v === '' || v === null || v === undefined) return null;
    if (declaredTypes.get(`${dataset}:${h}`) === 'string') return String(v);
    if (v === true || v === 'true') return true;
    if (v === false || v === 'false') return false;
    return numeric.has(h) ? Number(v) : String(v);
  }));
  csvFiles.push(relative);
  return { relative, headers, rows, records: rows.map(r => Object.fromEntries(headers.map((h, j) => [h, r[j]]))) };
}

const files = [
  'data/annual_aggregate.csv', 'data/annual_ratios.csv', 'data/bank_panel.csv', 'data/bank_ratios.csv',
  'data/central_bank_context.csv', 'data/price_context.csv', 'data/institution_crosswalk_1929.csv',
  'data/coverage_1929.csv', 'data/reserve_events.csv', 'metadata/variable_dictionary.csv',
  'metadata/source_index.csv', 'metadata/population_definitions.csv', 'metadata/dataset_index.csv',
];
const dictionary = await readCsv('metadata/variable_dictionary.csv');
for (const r of dictionary.records) declaredTypes.set(`${r.dataset_id}:${r.column_name}`, r.data_type);
const imported = [dictionary, ...await Promise.all(files.filter(x => x !== 'metadata/variable_dictionary.csv').map(readCsv))];
console.log('Imported the frozen CSV tables and metadata.');
const db = Object.fromEntries(imported.map(x => [path.basename(x.relative, '.csv'), x]));
for (const source of imported) for (const record of source.records) for (const field of source.headers) {
  const declared = declaredTypes.get(`${path.basename(source.relative, '.csv')}:${field}`);
  if (record[field] !== null && ['integer', 'number'].includes(declared)) {
    assert.equal(typeof record[field], 'number', `${source.relative}: ${field} must be numeric`);
    if (declared === 'integer') assert.ok(Number.isInteger(record[field]), `${source.relative}: ${field} must be integer`);
  }
}
const annual = db.annual_aggregate.records;
const banks = db.bank_panel.records;
const annualRatios = db.annual_ratios.records;
const bankRatios = db.bank_ratios.records;
assert.equal(annual.length, 19);
assert.equal(new Set(annual.map(r => r.year)).size, 19);
assert.equal(banks.length, 70);
const bankRegister = [...new Map(banks.map(r => [r.bank_id, { bank_id: r.bank_id, bank_name: r.bank_name,
  population_id: r.population_id }])).values()];
assert.equal(bankRegister.length, 14);
for (const r of bankRegister) assert.equal(banks.filter(b => b.bank_id === r.bank_id).length, 5);
assert.equal(annual.find(r => r.year === 1919).total_deposits, null);
assert.equal(annual.find(r => r.year === 1919).reported_deposits_total, 10740);
assert.equal(annual.find(r => r.year === 1936).income_balance_counts_match, false);

for (const name of sheets) {
  const s = ws[name];
  s.showGridLines = false;
  s.getRange('A1:N100').format.font = { name: FONT, size: 10, color: C.ink };
  s.getRange('A1:N100').format.verticalAlignment = 'center';
  s.getRange('A1:N100').format.rowHeight = 20;
}
ws.Explore.tabColor = C.ink;
ws['Read me'].tabColor = C.burgundy;
ws['Annual ratios'].tabColor = C.teal;
ws['Bank ratios'].tabColor = C.teal;
ws.Dictionary.tabColor = '#A79B85';

function title(s, text, note1 = '', note2 = '', lastCol = 'M') {
  s.getRange('A2').values = [[text]];
  s.getRange('A2').format.font = { name: FONT, size: 16, bold: true, color: C.ink };
  s.getRange(`A2:${lastCol}2`).format.rowHeight = 28;
  s.getRange(`A2:${lastCol}2`).format.borders = { bottom: { style: 'thin', color: C.burgundy } };
  if (note1) s.getRange('A3').values = [[note1]];
  if (note2) s.getRange('A4').values = [[note2]];
  s.getRange(`A3:${lastCol}4`).format.font = { name: FONT, size: 10, color: C.muted, italic: true };
}

function writeTable(s, startRow, records, fields, opts = {}) {
  const { name = s.name.replaceAll(/[^A-Za-z0-9]/g, '') + startRow, labels = {}, widths = {},
    formats = {}, wrap = [], source = '', recordKey = [] } = opts;
  const n = fields.length, last = startRow + records.length;
  s.getRange(`A${startRow}:${col(n)}${startRow}`).values = [fields.map(f => labels[f] || nice(f))];
  const data = records.map(r => fields.map(f => r[f] ?? null));
  s.getRange(`A${startRow + 1}:${col(n)}${last}`).values = data;
  s.getRange(`A${startRow}:${col(n)}${last}`).format.font = { name: FONT, size: 10, color: C.ink };
  s.getRange(`A${startRow}:${col(n)}${last}`).format.verticalAlignment = 'center';
  s.getRange(`A${startRow}:${col(n)}${startRow}`).format = {
    fill: C.ink, font: { name: FONT, size: 10, bold: true, color: C.white }, wrapText: true,
    horizontalAlignment: 'center', verticalAlignment: 'center', rowHeight: 48,
    borders: { insideVertical: { style: 'thin', color: C.white } },
  };
  for (let j = 0; j < n; j++) {
    const f = fields[j], letter = col(j + 1), values = data.map(r => r[j]).filter(v => v !== null);
    const numeric = values.length && values.every(v => typeof v === 'number');
    const integer = numeric && (/(?:year|count|page|row)$/.test(f) || f === 'year');
    const width = widths[f] || (f === 'year' ? 72 : f === 'bank_id' ? 122 : 112);
    const widthKey = `${s.name}!${letter}`;
    columnWidths[widthKey] = Math.max(columnWidths[widthKey] || 0, width);
    s.getRange(`${letter}${startRow}:${letter}${last}`).format.columnWidthPx = columnWidths[widthKey];
    s.getRange(`${letter}${startRow + 1}:${letter}${last}`).format.horizontalAlignment = integer ? 'center' : numeric ? 'right' : 'left';
    s.getRange(`${letter}${startRow + 1}:${letter}${last}`).setNumberFormat(formats[f] || (integer ? INT : numeric ? (values.every(Number.isInteger) ? '#,##0' : NUM) : 'General'));
    if (wrap.includes(f)) {
      s.getRange(`${letter}${startRow + 1}:${letter}${last}`).format.wrapText = true;
      s.getRange(`${letter}${startRow + 1}:${letter}${last}`).format.verticalAlignment = 'top';
    }
  }
  for (let i = 0; i < records.length; i++) {
    const row = startRow + i + 1;
    s.getRange(`A${row}:${col(n)}${row}`).format.rowHeight = 22;
    if (i % 2) s.getRange(`A${row}:${col(n)}${row}`).format.fill = C.light;
    if (wrap.length) {
      const lines = Math.max(1, ...wrap.map(f => Math.ceil(String(records[i][f] || '').length /
        Math.max(12, Math.floor((widths[f] || 112) / 5.6)))));
      s.getRange(`A${row}:${col(n)}${row}`).format.rowHeight = Math.min(230, Math.max(25, lines * 14 + 8));
    }
    if (source) fields.forEach((f, j) => inputCells.push({ sheet: s.name, address: `${col(j + 1)}${row}`,
      source, key: recordKey.map(k => records[i][k]).join(':'), variable: f, expected: records[i][f] ?? null }));
  }
  const table = s.tables.add(`A${startRow}:${col(n)}${last}`, true, name);
  table.style = 'TableStyleLight1';
  table.showFilterButton = true;
  table.showTotals = false;
  return { sheet: s.name, start: startRow + 1, end: last, fields,
    col: Object.fromEntries(fields.map((f, j) => [f, col(j + 1)])), table: name };
}

function coreSheet(name, heading, note, data, fields, opts = {}) {
  const s = ws[name];
  title(s, heading, 'Nominal millions of Kč. One row per source observation. Blank cells are not zero.', note, col(fields.length));
  const map = writeTable(s, 7, data, fields, opts);
  tableMaps[name] = map;
  s.freezePanes.freezeRows(7);
  s.freezePanes.freezeColumns(name.startsWith('Bank ') ? 2 : 1);
  renderPlan.push({ sheet: name, range: `A1:${col(fields.length)}${Math.min(map.end, 17)}`, suffix: 'opening' });
  if (map.end > 30) renderPlan.push({ sheet: name, range: `A${map.end - 7}:${col(fields.length)}${map.end}`, suffix: 'last_rows' });
  return map;
}

const labels = {
  year: 'Year', bank_id: 'Bank ID', balance_bank_count: 'Balance-sheet banks', income_bank_count: 'Income banks',
  total_assets: 'Total assets', broad_cash: 'Broad cash', cash: 'Source cash', loans_advances: 'Loans and advances',
  bills_discounted: 'Discounted bills', bills: 'Bills', identified_sundry_loans: 'Loans in sundry assets',
  loans_and_bills: 'Loans and bills', extended_credit: 'Extended credit', securities: 'Securities', participations: 'Participations',
  premises: 'Premises', sundry_assets: 'Sundry assets', other_assets: 'Other assets', debtors: 'Debtors', issue_loans: 'Issue loans',
  paid_capital: 'Paid share capital', loss_covering_reserves: 'Loss-cover reserves', published_reserves: 'Published reserves',
  capital_and_reserves: 'Capital and reserves', balance_sheet_profit: 'Balance-sheet profit',
  reported_deposits_total: 'Original deposit total', total_deposits: 'Comparable deposits', due_to_banks: 'Due to banks',
  sundry_liabilities: 'Sundry liabilities', deposits_comparable: 'Deposits comparable',
  income_balance_counts_match: 'Published counts match', net_interest: 'Net interest', commissions: 'Commissions',
  gross_profits: 'Gross profits', operating_expenses: 'Operating expenses', net_profit_loss: 'Net profit / loss',
  writeoffs: 'Write-offs', dividends: 'Dividends', other_funds: 'Other funds', source_deposits: 'Source deposits',
  general_creditors: 'General creditors', other_liabilities: 'Other liabilities', profit_carried_forward: 'Profit brought forward',
  reported_net_profit: 'Reported net profit', bonds_issued: 'Bonds issued', stabilization_fund: 'Stabilisation fund',
  other_income: 'Other income', overheads_nonstaff: 'Non-staff overheads', overheads_staff: 'Staff overheads',
  taxes: 'Taxes', depreciation: 'Depreciation', other_losses: 'Other losses',
};
coreSheet('Annual assets', 'Aggregate assets, 1919–1937',
  'League of Nations changing joint-stock-bank aggregate. Source IDs and entry locators: Source notes.', annual,
  ['year','balance_bank_count','total_assets','broad_cash','loans_advances','bills_discounted','identified_sundry_loans',
    'loans_and_bills','extended_credit','securities','participations','premises','sundry_assets'],
  { labels, source: 'data/annual_aggregate.csv', recordKey: ['year'] });
coreSheet('Annual funding', 'Aggregate funding and published capital',
  'The 1919 original deposit total includes unseparated bank creditors. Comparable deposits remain blank.', annual,
  ['year','balance_bank_count','paid_capital','loss_covering_reserves','capital_and_reserves','balance_sheet_profit',
    'reported_deposits_total','total_deposits','due_to_banks','sundry_liabilities','deposits_comparable'],
  { labels, source: 'data/annual_aggregate.csv', recordKey: ['year'] });
coreSheet('Annual income', 'Aggregate income accounts',
  '1936: 22 income accounts and 23 balance sheets. Income-to-assets ratios omit that year.', annual,
  ['year','income_bank_count','balance_bank_count','net_interest','commissions','gross_profits','operating_expenses',
    'net_profit_loss','writeoffs','dividends','income_balance_counts_match'],
  { labels, source: 'data/annual_aggregate.csv', recordKey: ['year'] });
coreSheet('Bank assets', 'Bank assets, 1933–1937',
  'Kašpar handbook cohort. Source cash and debtors retain the source meanings; see the Dictionary and Source notes.', banks,
  ['bank_id','year','total_assets','cash','bills','securities','participations','debtors','premises','other_assets','issue_loans'],
  { labels, source: 'data/bank_panel.csv', recordKey: ['bank_id','year'] });
coreSheet('Bank funding', 'Bank funding and published capital',
  'Source deposits include mortgage borrowing at Legiobanka. General creditors are not exclusively interbank.', banks,
  ['bank_id','year','paid_capital','published_reserves','other_funds','source_deposits','general_creditors',
    'other_liabilities','profit_carried_forward','reported_net_profit','bonds_issued','stabilization_fund'],
  { labels, source: 'data/bank_panel.csv', recordKey: ['bank_id','year'] });
coreSheet('Bank income', 'Bank income accounts',
  'Annual flows, as classified in the consulted handbook retyping. Income intensity is not a net interest margin.', banks,
  ['bank_id','year','net_interest','commissions','other_income','overheads_nonstaff','overheads_staff','taxes','depreciation','other_losses'],
  { labels, source: 'data/bank_panel.csv', recordKey: ['bank_id','year'] });

function fieldRange(sheet, field) {
  const m = tableMaps[sheet];
  assert.ok(m?.col[field], `${sheet}: missing field ${field}`);
  return `${quote(sheet)}!$${m.col[field]}$${m.start}:$${m.col[field]}$${m.end}`;
}
function aSum(sheet, field, year) { return `SUMIFS(${fieldRange(sheet,field)},${fieldRange(sheet,'year')},${year})`; }
function bSum(sheet, field, bank, year) { return `SUMIFS(${fieldRange(sheet,field)},${fieldRange(sheet,'bank_id')},${bank},${fieldRange(sheet,'year')},${year})`; }
function aFlag(sheet, field, year) { return `INDEX(${fieldRange(sheet,field)},MATCH(${year},${fieldRange(sheet,'year')},0))`; }

const aRatioFields = ['capital_assets_pct','loans_bills_assets_pct','extended_credit_assets_pct','cash_assets_pct',
  'securities_assets_pct','participations_assets_pct','deposits_assets_pct','bank_creditors_assets_pct',
  'loans_bills_deposits_pct','net_interest_assets_pct','commissions_assets_pct','net_profit_assets_pct'];
const ratioLabels = {
  capital_assets_pct: 'Capital / assets (%)', loans_bills_assets_pct: 'Loans + bills / assets (%)',
  extended_credit_assets_pct: 'Extended credit / assets (%)', cash_assets_pct: 'Cash / assets (%)',
  securities_assets_pct: 'Securities / assets (%)', participations_assets_pct: 'Participations / assets (%)',
  deposits_assets_pct: 'Deposits / assets (%)', bank_creditors_assets_pct: 'Due to banks / assets (%)',
  loans_bills_deposits_pct: 'Loans + bills / deposits (%)', net_interest_assets_pct: 'Net interest / end-assets (%)',
  commissions_assets_pct: 'Commissions / end-assets (%)', net_profit_assets_pct: 'Net profit / end-assets (%)',
  debtors_and_bills: 'Debtors and bills', debtors_bills_assets_pct: 'Debtors + bills / assets (%)',
  source_deposits_assets_pct: 'Source deposits / assets (%)', general_creditors_assets_pct: 'Creditors / assets (%)',
};
title(ws['Annual ratios'], 'Annual ratios and income intensity',
  'Percentages are stored in percentage units: a value of 9.70 means 9.70 per cent.',
  'Formulas reference the account sheets by year. 1919 deposit ratios and 1936 income ratios remain blank.');
tableMaps['Annual ratios'] = writeTable(ws['Annual ratios'], 7,
  annual.map(r => ({ year: r.year })), ['year',...aRatioFields],
  { labels: { year:'Year',...ratioLabels }, formats: Object.fromEntries(aRatioFields.map(f => [f,RATIO])) });
const aSpecs = {
  capital_assets_pct:['Annual funding','capital_and_reserves'], loans_bills_assets_pct:['Annual assets','loans_and_bills'],
  extended_credit_assets_pct:['Annual assets','extended_credit'], cash_assets_pct:['Annual assets','broad_cash'],
  securities_assets_pct:['Annual assets','securities'], participations_assets_pct:['Annual assets','participations'],
  deposits_assets_pct:['Annual funding','total_deposits'], bank_creditors_assets_pct:['Annual funding','due_to_banks'],
  loans_bills_deposits_pct:['Annual assets','loans_and_bills'], net_interest_assets_pct:['Annual income','net_interest'],
  commissions_assets_pct:['Annual income','commissions'], net_profit_assets_pct:['Annual income','net_profit_loss'],
};
for (let j=0;j<aRatioFields.length;j++) {
  const metric=aRatioFields[j], [source,field]=aSpecs[metric], letter=col(j+2);
  const formulas=annual.map((r,i)=>{
    const row=i+8, yr=`$A${row}`;
    const denominator=metric==='loans_bills_deposits_pct'?aSum('Annual funding','total_deposits',yr):aSum('Annual assets','total_assets',yr);
    let expr=`100*${aSum(source,field,yr)}/${denominator}`;
    if (['deposits_assets_pct','bank_creditors_assets_pct','loans_bills_deposits_pct'].includes(metric))
      expr=`IF(${aFlag('Annual funding','deposits_comparable',yr)},${expr},"")`;
    if (source==='Annual income') expr=`IF(${aFlag('Annual income','income_balance_counts_match',yr)},${expr},"")`;
    formulaChecks.push({sheet:'Annual ratios',address:`${letter}${row}`,expected:annualRatios.find(x=>x.year===r.year)[metric],metric,year:r.year});
    return ['='+expr];
  });
  ws['Annual ratios'].getRange(`${letter}8:${letter}26`).formulas=formulas;
  ws['Annual ratios'].getRange(`${letter}8:${letter}26`).setNumberFormat(RATIO);
  ws['Annual ratios'].getRange(`${letter}8:${letter}26`).format.horizontalAlignment='right';
}
ws['Annual ratios'].freezePanes.freezeRows(7);ws['Annual ratios'].freezePanes.freezeColumns(1);
renderPlan.push({sheet:'Annual ratios',range:'A1:M18',suffix:'opening'},{sheet:'Annual ratios',range:'A21:M26',suffix:'late_years'});

const bRatioFields=['total_assets','capital_and_reserves','debtors_and_bills','capital_assets_pct','debtors_bills_assets_pct',
  'cash_assets_pct','securities_assets_pct','source_deposits_assets_pct','general_creditors_assets_pct','net_interest_assets_pct','commissions_assets_pct'];
title(ws['Bank ratios'],'Bank ratios and income intensity',
  'Stocks are millions of Kč. Ratio columns contain percentage units, with end-year assets as denominator.',
  'Keyed formulas preserve the bank ID and year. The denominator and the two principal numerators are visible.');
tableMaps['Bank ratios']=writeTable(ws['Bank ratios'],7,banks.map(r=>({bank_id:r.bank_id,year:r.year})),['bank_id','year',...bRatioFields],
  {labels:{...labels,...ratioLabels},formats:Object.fromEntries(bRatioFields.filter(x=>x.endsWith('_pct')).map(f=>[f,RATIO]))});
for(let j=0;j<bRatioFields.length;j++) {
  const metric=bRatioFields[j],letter=col(j+3);
  const formulas=banks.map((r,i)=>{
    const row=i+8,id=`$A${row}`,yr=`$B${row}`;
    const asset=bSum('Bank assets','total_assets',id,yr),capital=`${bSum('Bank funding','paid_capital',id,yr)}+${bSum('Bank funding','published_reserves',id,yr)}`;
    let expr;
    if(metric==='total_assets')expr=asset;
    else if(metric==='capital_and_reserves')expr=capital;
    else if(metric==='debtors_and_bills')expr=`${bSum('Bank assets','debtors',id,yr)}+${bSum('Bank assets','bills',id,yr)}`;
    else if(metric==='capital_assets_pct')expr=`100*$D${row}/$C${row}`;
    else if(metric==='debtors_bills_assets_pct')expr=`100*$E${row}/$C${row}`;
    else {
      const map={cash_assets_pct:['Bank assets','cash'],securities_assets_pct:['Bank assets','securities'],
        source_deposits_assets_pct:['Bank funding','source_deposits'],general_creditors_assets_pct:['Bank funding','general_creditors'],
        net_interest_assets_pct:['Bank income','net_interest'],commissions_assets_pct:['Bank income','commissions']};
      expr=`100*${bSum(...map[metric],id,yr)}/$C${row}`;
    }
    const expected=metric==='total_assets'?r.total_assets:bankRatios.find(x=>x.bank_id===r.bank_id&&x.year===r.year)[metric];
    formulaChecks.push({sheet:'Bank ratios',address:`${letter}${row}`,expected,metric,bank_id:r.bank_id,year:r.year});
    return ['='+expr];
  });
  ws['Bank ratios'].getRange(`${letter}8:${letter}77`).formulas=formulas;
  ws['Bank ratios'].getRange(`${letter}8:${letter}77`).setNumberFormat(metric.endsWith('_pct')?RATIO:NUM);
  ws['Bank ratios'].getRange(`${letter}8:${letter}77`).format.horizontalAlignment='right';
}
ws['Bank ratios'].freezePanes.freezeRows(7);ws['Bank ratios'].freezePanes.freezeColumns(2);
renderPlan.push({sheet:'Bank ratios',range:'A1:M16',suffix:'opening'},{sheet:'Bank ratios',range:'A70:M77',suffix:'last_rows'});

// Context tables retain their own populations and units.
title(ws['Monetary context'],'Central-bank and price context',
  'These are separate contextual populations. They are not components of the commercial-bank sample.',
  'Central-bank amounts are nominal millions of Kč. Price-index bases and timing are identified below.');
writeTable(ws['Monetary context'],7,db.central_bank_context.records,
  ['year','total_assets','notes_in_circulation','discounted_bills','discounted_securities','advances_on_collateral','source_id','source_pages'],
  {name:'CentralBankContext',labels:{...labels,notes_in_circulation:'Notes in circulation',discounted_bills:'Discounted bills',
    discounted_securities:'Discounted securities',advances_on_collateral:'Collateral advances',source_id:'Source ID',source_pages:'Source pages'},
    widths:{source_id:150,source_pages:180},source:'data/central_bank_context.csv',recordKey:['year']});
ws['Monetary context'].getRange('A20').values=[['Price observations and timing']];
ws['Monetary context'].getRange('A20').format.font={name:FONT,size:12,bold:true,color:C.burgundy};
ws['Monetary context'].getRange('A21').values=[['WPI stock proxy is the following 1 January. The annual WPI uses monthly observations. CPI timing is source-specific.']];
const priceFields=['year','wpi_available_months','wpi_annual_mean','wpi_december_first','wpi_year_end_proxy',
  'wpi_year_end_proxy_1929_100','cpi_source_index','cpi_1929_100','wpi_proxy_source_date','cpi_source_cell','flags'];
writeTable(ws['Monetary context'],23,db.price_context.records,priceFields,
  {name:'PriceContext',labels:{year:'Year',wpi_available_months:'WPI monthly count',wpi_annual_mean:'WPI annual mean',
    wpi_december_first:'WPI 1 December',wpi_year_end_proxy:'WPI next 1 January',wpi_year_end_proxy_1929_100:'WPI proxy (1929=100)',
    cpi_source_index:'CPI source index',cpi_1929_100:'CPI (1929=100)',wpi_proxy_source_date:'WPI proxy date',
    cpi_source_cell:'CPI workbook cell',flags:'Source flags'},widths:{flags:350,wpi_proxy_source_date:115},
    wrap:['flags'],source:'data/price_context.csv',recordKey:['year']});
ws['Monetary context'].getRange('I24:I43').format.horizontalAlignment='center';
ws['Monetary context'].freezePanes.freezeRows(7);ws['Monetary context'].freezePanes.freezeColumns(1);
renderPlan.push({sheet:'Monetary context',range:'A1:H17',suffix:'central_bank'},
  {sheet:'Monetary context',range:'A20:K34',suffix:'prices_early'},{sheet:'Monetary context',range:'A35:K44',suffix:'prices_late'});

// Bank register plus the dated national comparison, never a claim of later LoN membership.
title(ws.Institutions,'Institutions and the 1929 national comparison',
  'Fourteen handbook institutions have counterparts in the 1929 national roster. The dated comparison is separate from 1933–1937 coverage.',
  'Stable bank IDs are used throughout the workbook. National amounts below retain the source unit: thousand Kč.');
writeTable(ws.Institutions,7,bankRegister,['bank_id','bank_name','population_id'],{name:'BankRegister',
  labels:{bank_id:'Bank ID',bank_name:'Handbook institution',population_id:'Population ID'},
  widths:{bank_id:122,bank_name:390,population_id:280},source:'data/bank_panel.csv',recordKey:['bank_id']});
ws.Institutions.getRange('A24').values=[['Dated coverage controls, 1929']];
ws.Institutions.getRange('A24').format.font={name:FONT,size:12,bold:true,color:C.burgundy};
writeTable(ws.Institutions,26,db.coverage_1929.records,
  ['label','unit','national_22_total','matched_14_total','unmatched_8_total','matched_share_percent'],
  {name:'Coverage1929',labels:{label:'Measure',unit:'Unit',national_22_total:'National 22',matched_14_total:'Matched 14',
    unmatched_8_total:'Other 8',matched_share_percent:'Matched share (%)'},widths:{label:290,unit:170},
    formats:{matched_share_percent:RATIO},source:'data/coverage_1929.csv',recordKey:['measure']});
ws.Institutions.getRange('A36').values=[['National roster and institution links']];
ws.Institutions.getRange('A36').format.font={name:FONT,size:12,bold:true,color:C.burgundy};
ws.Institutions.getRange('A37').values=[['Printed dashes in the accepted national transcription are coded zero. Absence from the panel does not itself establish failure or exit.']];
writeTable(ws.Institutions,39,db.institution_crosswalk_1929.records,
  ['national_bank_id','national_bank_name','national_headquarters','included_in_1933_1937_panel','panel_bank_id',
    'paid_capital_thousand_kc','loss_cover_reserves_thousand_kc','book_and_cash_certificate_deposits_thousand_kc',
    'creditors_thousand_kc','own_bonds_thousand_kc','match_class'],
  {name:'NationalInstitutions1929',labels:{national_bank_id:'National ID',national_bank_name:'National institution',
    national_headquarters:'Headquarters',included_in_1933_1937_panel:'Panel member',panel_bank_id:'Panel bank ID',
    paid_capital_thousand_kc:'Paid capital (000 Kč)',loss_cover_reserves_thousand_kc:'Reserves (000 Kč)',
    book_and_cash_certificate_deposits_thousand_kc:'Deposits (000 Kč)',creditors_thousand_kc:'Creditors (000 Kč)',
    own_bonds_thousand_kc:'Own bonds (000 Kč)',match_class:'Identity match'},
    widths:{national_bank_name:390,national_headquarters:120,match_class:290},wrap:['national_bank_name','match_class'],
    source:'data/institution_crosswalk_1929.csv',recordKey:['national_bank_id']});
ws.Institutions.freezePanes.freezeRows(7);ws.Institutions.freezePanes.freezeColumns(1);
renderPlan.push({sheet:'Institutions',range:'A1:C22',suffix:'register'},{sheet:'Institutions',range:'A24:F34',suffix:'coverage'},
  {sheet:'Institutions',range:'A36:K46',suffix:'national_roster'});

// Full release dictionary is preserved even for canonical tables not duplicated in Excel.
title(ws.Dictionary,'Variable dictionary',
  'The complete release dictionary covers every public CSV column. Dataset IDs identify the canonical tables.',
  'The workbook is a curated account and indicator view. Full long-form observations and cell lineage remain in the CSV release.');
const dictionaryFields=db.variable_dictionary.headers;
const dictWidths={dataset_id:165,column_name:245,label:200,description:440,data_type:90,unit:150,role:160,formula:320,
  original_source_label:220,input_source_column:220,missing_value_encoding:220,status_detail_location:280};
writeTable(ws.Dictionary,7,db.variable_dictionary.records,dictionaryFields,{name:'VariableDictionary',widths:dictWidths,
  wrap:dictionaryFields,source:'metadata/variable_dictionary.csv',recordKey:['dataset_id','column_name']});
ws.Dictionary.freezePanes.freezeRows(7);ws.Dictionary.freezePanes.freezeColumns(2);
renderPlan.push({sheet:'Dictionary',range:'A1:F13',suffix:'definitions'},{sheet:'Dictionary',range:'G7:L14',suffix:'lineage_columns'},
  {sheet:'Dictionary',range:`A${db.variable_dictionary.records.length}:F${db.variable_dictionary.records.length+7}`,suffix:'last_rows'});

// Bibliographic identities and source locators sit with the provenance records.
title(ws['Source notes'],'Sources and record provenance',
  'Source codes identify publications and consulted editions. This workbook does not bundle scans.',
  'Kašpar bank values come from a modern retyping with PDF metadata dated 2006. Original annual reports have not been verified.');
const sourceFields=['source_id','publication_year','title','source_url','consulted_edition','verification_scope'];
writeTable(ws['Source notes'],7,db.source_index.records,sourceFields,{name:'SourceIndex',
  widths:{source_id:230,publication_year:80,title:340,source_url:310,consulted_edition:310,verification_scope:390},
  wrap:sourceFields,source:'metadata/source_index.csv',recordKey:['source_id']});
const apStart=21;
ws['Source notes'].getRange(`A${apStart}`).values=[['Annual observation provenance']];
ws['Source notes'].getRange(`A${apStart}`).format.font={name:FONT,size:12,bold:true,color:C.burgundy};
writeTable(ws['Source notes'],apStart+2,annual,['year','population_id','source_ids','source_entry_ids','flags'],
  {name:'AnnualProvenance',widths:{year:72,population_id:260,source_ids:200,source_entry_ids:460,flags:350},
    wrap:['population_id','source_ids','source_entry_ids','flags'],source:'data/annual_aggregate.csv',recordKey:['year']});
const bpStart=47;
ws['Source notes'].getRange(`A${bpStart}`).values=[['Bank-year source pages and flags']];
ws['Source notes'].getRange(`A${bpStart}`).format.font={name:FONT,size:12,bold:true,color:C.burgundy};
writeTable(ws['Source notes'],bpStart+2,banks,['bank_id','year','asset_pdf_page','liability_pdf_page','income_pdf_page',
  'asset_component_residual','flags','category_notes'],{name:'BankProvenance',
    labels:{bank_id:'Bank ID',year:'Year',asset_pdf_page:'Asset PDF page',liability_pdf_page:'Funding PDF page',
      income_pdf_page:'Income PDF page',asset_component_residual:'Asset component residual (m Kč)',flags:'Source flags',category_notes:'Category notes'},
    widths:{bank_id:122,year:72,asset_pdf_page:90,liability_pdf_page:90,income_pdf_page:90,asset_component_residual:130,flags:290,category_notes:460},
    wrap:['flags','category_notes'],source:'data/bank_panel.csv',recordKey:['bank_id','year']});
const evStart=124;
ws['Source notes'].getRange(`A${evStart}`).values=[['Dated reserve and capital events']];
ws['Source notes'].getRange(`A${evStart}`).format.font={name:FONT,size:12,bold:true,color:C.burgundy};
writeTable(ws['Source notes'],evStart+2,db.reserve_events.records,
  ['bank_id','year','amount_million_kc','amount_status','event_description','interpretation','source_pdf_pages'],
  {name:'ReserveEvents',labels:{bank_id:'Bank ID',year:'Year',amount_million_kc:'Amount (m Kč)',amount_status:'Amount status',
    event_description:'Recorded event',interpretation:'Interpretation',source_pdf_pages:'Source PDF pages'},
    widths:{bank_id:122,year:72,amount_million_kc:130,amount_status:240,event_description:340,interpretation:470,source_pdf_pages:130},
    wrap:['amount_status','event_description','interpretation'],source:'data/reserve_events.csv',recordKey:['event_id']});
ws['Source notes'].freezePanes.freezeRows(7);ws['Source notes'].freezePanes.freezeColumns(1);
renderPlan.push({sheet:'Source notes',range:'A1:F12',suffix:'publications'},{sheet:'Source notes',range:'A21:E29',suffix:'annual_provenance'},
  {sheet:'Source notes',range:'A47:H57',suffix:'bank_provenance'},{sheet:'Source notes',range:'A124:G132',suffix:'events'});

// Compact guide and navigation. Counts describe unique core observations.
const guide=ws['Read me'];
title(guide,'Using the banking dataset workbook','Version 0.1.0. Public release, 29 October 2026.','Primary scope: joint-stock commercial banking in Bohemia, Moravia and Silesia.');
const guideRows=[
  ['Core annual series','19 annual observations, 1919–1937. The League aggregate has changing membership.'],
  ['Bank panel','70 bank-year observations: 14 named institutions observed in each year, 1933–1937.'],
  ['Units','Account stocks and income flows are nominal millions of Czechoslovak crowns (Kč), unless a header states another unit. Decimal values are displayed to three places; cells retain full precision.'],
  ['Ratio units','Ratios are stored in percentage units: 9.70 means 9.70 per cent. Charts use fixed-base indices.'],
  ['Missing values','Blank means unavailable or not comparable. It is never an implicit zero. The national 1929 roster separately preserves its printed-dash convention.'],
  ['1919 deposits','Original reported deposits are 10,740 million Kč and include unseparated bank creditors. Comparable deposits and related ratios are blank.'],
  ['1936 income','Income counts 22 banks; balance sheets count 23. Income divided by assets is therefore suppressed in that year. Equal counts in other years do not prove identical membership.'],
  ['Source categories','Loans, bills, cash, creditors and deposits retain the published category boundaries. They do not isolate domestic nonfinancial-customer credit or economic loss-bearing capital.'],
  ['Population comparison','The fixed handbook cohort and the changing League aggregate are separate datasets. The 1929 crosswalk measures a dated national footprint.'],
  ['Handbook edition','Bank tables were read from a modern retyping of Kašpar’s handbook, with PDF metadata dated 2006. Original annual reports have not been verified.'],
  ['Workbook controls','The bank selector on Explore changes the selected institution. Account tables remain visible, unprotected source values. Formulas use year and bank keys.'],
  ['Canonical release','CSV files preserve the canonical field names, full detail, long observations and cell-level lineage. This workbook partitions account fields into readable views.'],
  ['Price context','CPI and WPI are distinct price concepts. The stock-date WPI proxy uses the following 1 January. Raw source indices and 1929=100 versions remain separate.'],
  ['Rebuild','Run code/build_dataset.py for the CSV release, then code/build_workbook.mjs with the artifact-tool Node runtime.'],
];
writeTable(guide,7,guideRows.map(([topic,detail])=>({topic,detail})),['topic','detail'],{name:'WorkbookGuide',
  labels:{topic:'Topic',detail:'Definition or use'},widths:{topic:190,detail:820},wrap:['detail']});
guide.getRange('A25').values=[['Workbook navigation']];guide.getRange('A25').format.font={name:FONT,size:12,bold:true,color:C.burgundy};
const nav=sheets.filter(x=>x!=='Read me').map(x=>({worksheet:x,purpose:({Explore:'Two historical charts and a bank selector.',
  'Annual assets':'Assets, credit categories and balance-sheet counts.','Annual funding':'Liabilities, original deposits and published capital.',
  'Annual income':'Income, expenses, dividends and source counts.','Annual ratios':'Formula-based ratios with explicit population exclusions.',
  'Bank assets':'The 70 bank-year asset observations.','Bank funding':'The 70 bank-year funding and capital observations.',
  'Bank income':'The 70 bank-year income observations.','Bank ratios':'Formula-based capital, portfolio and income measures.',
  'Monetary context':'Central-bank accounts and price observations.','Institutions':'Stable IDs, national roster and dated coverage.',
  Dictionary:'Full public-variable definitions and source mapping.','Source notes':'Publication identities, record flags and source-page locators.'})[x]}));
writeTable(guide,27,nav,['worksheet','purpose'],{name:'Navigation',labels:{worksheet:'Worksheet',purpose:'Contents'},
  widths:{worksheet:190,purpose:820}});
guide.getRange('A28:A40').format.font={name:FONT,size:10,bold:true,color:C.burgundy};
renderPlan.push({sheet:'Read me',range:'A1:B22',suffix:'guide'},{sheet:'Read me',range:'A25:B41',suffix:'navigation'});

// Two native, cell-linked historical charts. The single selector belongs here.
const explore=ws.Explore;
explore.getRange('A1:N55').format.fill=C.paper;
explore.getRange('A1:N55').format.font={name:FONT,size:10,color:C.ink};
explore.getRange('A1:A55').format.columnWidthPx=24;
explore.getRange('B1:G55').format.columnWidthPx=96;
explore.getRange('H1:H55').format.columnWidthPx=28;
explore.getRange('I1:N55').format.columnWidthPx=96;
explore.getRange('B2').values=[['Commercial banking in the Czech lands']];
explore.getRange('B2').format.font={name:FONT,size:16,bold:true,color:C.ink};
explore.getRange('B2:N2').format.rowHeight=30;
explore.getRange('B2:N2').format.borders={bottom:{style:'thin',color:C.burgundy}};
explore.getRange('B3').values=[['Version 0.1.0. Annual aggregate: 1919–1937. Fixed handbook cohort: 1933–1937.']];
explore.getRange('B3:N3').format.font={name:FONT,size:10,color:C.muted};
explore.getRange('B5').values=[['Changing aggregate']];explore.getRange('I5').values=[['Fixed bank cohort']];
explore.getRange('B5:N5').format.font={name:FONT,size:12,bold:true,color:C.burgundy};
explore.getRange('B6').values=[['Years']];explore.getRange('C6').formulas=[['=COUNT(\'Annual assets\'!$A$8:$A$26)']];
explore.getRange('C6').format.horizontalAlignment='left';
explore.getRange('D6').values=[['Base year']];explore.getRange('E6').values=[[1930]];
explore.getRange('I6').values=[['Bank ID']];explore.getRange('J6').values=[['zivno']];
explore.getRange('J6').format={fill:C.amber,font:{name:FONT,size:10,bold:true,color:C.ink},
  borders:{preset:'outside',style:'thin',color:C.burgundy},horizontalAlignment:'left'};
explore.getRange('J6').dataValidation={rule:{type:'list',values:bankRegister.map(r=>r.bank_id)}};
explore.getRange('K6').values=[['Editable selector']];explore.getRange('K6').format.font={name:FONT,size:10,italic:true,color:C.muted};
explore.getRange('B8').values=[['Nominal stocks. Each series equals 100 in 1930.']];
explore.getRange('I8').formulas=[['=IF($J$31=5,VLOOKUP($J$6,\'Institutions\'!$A$8:$B$21,2,FALSE),"Select a bank ID")']];
explore.getRange('B8:N8').format.font={name:FONT,size:10,color:C.muted};
explore.getRange('B29').values=[['The populations and category boundaries differ. Indexing does not make them interchangeable.']];
explore.getRange('B30').values=[['Blank observations remain blank. Account tables, definitions and provenance are available through Read me.']];
explore.getRange('B29:N30').format.font={name:FONT,size:10,color:C.muted};
explore.getRange('I31').values=[['Selected rows']];
explore.getRange('J31').formulas=[[`=COUNTIFS(${fieldRange('Bank assets','bank_id')},$J$6)`]];
explore.getRange('B33').values=[['Chart data and index calculations']];
explore.getRange('B33:N33').format.font={name:FONT,size:10,bold:true,color:C.ink};
explore.getRange('B34:E34').values=[['Year','Assets','Loans + bills','Capital + reserves']];
explore.getRange('I34:N34').values=[['Year','Assets','Debtors + bills','Capital + reserves','Net interest','Commissions']];
for (const area of ['B34:E34','I34:N34']) explore.getRange(area).format={fill:C.ink,font:{name:FONT,size:10,bold:true,color:C.white},wrapText:true,rowHeight:36,horizontalAlignment:'center'};
for(let i=0;i<annual.length;i++) {
  const row=35+i,yr=annual[i].year;
  explore.getRange(`B${row}`).values=[[yr]];
  const stock=[['Annual assets','total_assets'],['Annual assets','loans_and_bills'],['Annual funding','capital_and_reserves']];
  const formulas=stock.map(([s,f])=>`=100*${aSum(s,f,`$B${row}`)}/${aSum(s,f,'$E$6')}`);
  explore.getRange(`C${row}:E${row}`).formulas=[formulas];
  ['assets_index_1930_100','loans_bills_index_1930_100','capital_reserves_index_1930_100'].forEach((metric,j)=>
    formulaChecks.push({sheet:'Explore',address:`${col(j+3)}${row}`,expected:annualRatios.find(r=>r.year===yr)[metric]}));
}
for(let i=0;i<5;i++) {
  const row=35+i,yr=1933+i;
  explore.getRange(`I${row}`).values=[[yr]];
  const bankStock=(metric,year)=>metric==='capital_and_reserves'?`(${bSum('Bank funding','paid_capital','$J$6',year)}+${bSum('Bank funding','published_reserves','$J$6',year)})`:
    metric==='debtors_and_bills'?`(${bSum('Bank assets','debtors','$J$6',year)}+${bSum('Bank assets','bills','$J$6',year)})`:
    bSum(metric==='total_assets'?'Bank assets':'Bank income',metric,'$J$6',year);
  const stocks=['total_assets','debtors_and_bills','capital_and_reserves','net_interest','commissions'];
  explore.getRange(`J${row}:N${row}`).formulas=[stocks.map(m=>`=IF($J$31=5,IF(${bankStock(m,'1933')}=0,"",100*${bankStock(m,`$I${row}`)}/${bankStock(m,'1933')}),"")`)];
  const metrics=['assets_index_1933_100','debtors_bills_index_1933_100','capital_reserves_index_1933_100','net_interest_index_1933_100','commissions_index_1933_100'];
  metrics.forEach((metric,j)=>formulaChecks.push({sheet:'Explore',address:`${col(j+10)}${row}`,
    expected:bankRatios.find(r=>r.bank_id==='zivno'&&r.year===yr)[metric]}));
}
explore.getRange('B35:B53').setNumberFormat('0');explore.getRange('I35:I39').setNumberFormat('0');
explore.getRange('C35:E53').setNumberFormat('0.00');explore.getRange('J35:N39').setNumberFormat('0.00');
explore.getRange('C35:E53').format.horizontalAlignment='right';explore.getRange('J35:N39').format.horizontalAlignment='right';
const chartSpecs=[['B34:E53','B10','G27','Aggregate stocks (1930 = 100)'],['I34:L39','I10','N27','Selected bank (1933 = 100)']];
for(const [range,from,to,heading] of chartSpecs) {
  const chart=explore.charts.add('line',explore.getRange(range));chart.setPosition(from,to);chart.title=heading;
  chartObjects.push(chart);
  chart.titleTextStyle.typeface=FONT;chart.titleTextStyle.fontSize=16;
  chart.legend={position:'top',textStyle:{typeface:FONT,fontSize:12}};
  chart.xAxis={axisType:'textAxis',textStyle:{typeface:FONT,fontSize:12}};
  chart.yAxis={numberFormatCode:'0',numberFormatSourceLinked:false,textStyle:{typeface:FONT,fontSize:12}};
  chart.series.items.forEach((s,j)=>{const color=[C.ink,C.burgundy,C.teal][j];s.fill=color;s.line={fill:color,style:'solid',width:2};});
}
formulaChecks.push({sheet:'Explore',address:'C6',expected:19},{sheet:'Explore',address:'J31',expected:5},
  {sheet:'Explore',address:'I8',expected:bankRegister.find(r=>r.bank_id==='zivno').bank_name});
renderPlan.unshift({sheet:'Explore',range:'A1:N31',suffix:'dashboard'},{sheet:'Explore',range:'B33:N53',suffix:'calculations'});

// Final calculation and comprehensive checks against canonical CSV values.
wb.recalculate();
console.log('Calculated the workbook; checking source values and derived ratios.');
for(const item of inputCells) equalValue(ws[item.sheet].getRange(item.address).values[0][0],item.expected,`${item.sheet}!${item.address} ${item.variable}`,1e-12);
for(const item of formulaChecks) equalValue(ws[item.sheet].getRange(item.address).values[0][0],item.expected,`${item.sheet}!${item.address} ${item.metric||''}`);
console.log(`Validated ${inputCells.length} source cells and ${formulaChecks.length} derived cells.`);
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',
  options:{useRegex:true,maxResults:300},summary:'Workbook formula-error scan',maxChars:6000});
await fs.mkdir(outputDir,{recursive:true});await fs.mkdir(qaDir,{recursive:true});
await fs.writeFile(path.join(qaDir,'formula_error_scan.ndjson'),errors.ndjson);
const inspection=await wb.inspect({kind:'table',range:'Explore!I31:N39',include:'values,formulas',tableMaxRows:10,tableMaxCols:6,maxChars:6000});
await fs.writeFile(path.join(qaDir,'explorer_inspection.ndjson'),inspection.ndjson);
await fs.writeFile(path.join(qaDir,'workbook_table_map.json'),JSON.stringify(tableMaps,null,2));
await fs.writeFile(path.join(qaDir,'input_cell_manifest.json'),JSON.stringify(inputCells,null,2));
await fs.writeFile(path.join(qaDir,'formula_checks.json'),JSON.stringify(formulaChecks,null,2));
const activeRenderPlan=args['render-scope']==='publication'?renderPlan.filter(s=>(s.sheet==='Explore'&&s.suffix==='dashboard')||(s.sheet==='Read me'&&s.suffix==='guide')):renderPlan;
for(const spec of activeRenderPlan) {
  console.log(`Rendering ${spec.sheet}: ${spec.suffix}`);
  const blob=await wb.render({sheetName:spec.sheet,range:spec.range,scale:1,format:'png'});
  const filename=`${spec.sheet.toLowerCase().replaceAll(' ','_')}_${spec.suffix}.png`;
  await fs.writeFile(path.join(qaDir,filename),new Uint8Array(await blob.arrayBuffer()));
}
const xlsx=await SpreadsheetFile.exportXlsx(wb);await xlsx.save(outputPath);

// The disposable round-trip workbook tests actual formula response after export.
const probe=await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const probeExplore=probe.worksheets.getItem('Explore');
probeExplore.getRange('J6').values=[['agrarni']];
const sourceRow=banks.findIndex(r=>r.bank_id==='agrarni'&&r.year===1937)+8;
const original=banks.find(r=>r.bank_id==='agrarni'&&r.year===1937).total_assets;
const edited=original*1.1;
probe.worksheets.getItem('Bank assets').getRange(`C${sourceRow}`).values=[[edited]];
probe.recalculate();
const expectedIndex=100*edited/banks.find(r=>r.bank_id==='agrarni'&&r.year===1933).total_assets;
equalValue(probeExplore.getRange('J39').values[0][0],expectedIndex,'Disposable selector and asset edit');
const expectedCapital=100*(banks.find(r=>r.bank_id==='agrarni'&&r.year===1937).paid_capital+
  banks.find(r=>r.bank_id==='agrarni'&&r.year===1937).published_reserves)/edited;
equalValue(probe.worksheets.getItem('Bank ratios').getRange(`F${sourceRow}`).values[0][0],expectedCapital,'Disposable capital ratio response');
equalValue(ws['Bank assets'].getRange(`C${sourceRow}`).values[0][0],original,'Original source value preserved');
equalValue(ws.Explore.getRange('J6').values[0][0],'zivno','Original selector preserved');
probeExplore.getRange('J6').values=[['unknown_bank']];probe.recalculate();
equalValue(probeExplore.getRange('J39').values[0][0],'','Unmatched bank selector stays unavailable');
equalValue(probeExplore.getRange('I8').values[0][0],'Select a bank ID','Unmatched bank selector guidance');

const chartBindings=chartObjects.map(chart=>({title:chart.title.text,type:chart.type,
  series:chart.series.items.map(s=>({formula:s.formula,categoryFormula:s.categoryFormula}))}));
const qa={version:'0.1.0',status:'public release',output:path.basename(outputPath),sheets:sheets.length,sheet_names:sheets,
  core_annual_observations:19,bank_year_observations:70,bank_institutions:14,central_bank_observations:9,
  price_year_rows:20,national_roster_institutions:22,dictionary_rows:db.variable_dictionary.records.length,
  validated_source_cells:inputCells.length,validated_formula_cells:formulaChecks.length,chart_count:2,chart_bindings:chartBindings,
  numeric_tolerance:{source_relative:1e-12,derived_relative:1e-8},
  missing_data_checks:['1919 comparable deposits blank; original 10740 retained','1936 income-to-assets ratios blank','Unknown bank selector unavailable, not zero'],
  disposable_round_trip_test:{selected_bank:'agrarni',source_edit:'1937 total assets multiplied by 1.1',expected_asset_index:expectedIndex,
    expected_capital_assets_percent:expectedCapital,passed:true,final_original_unchanged:true},
  rendered_views:activeRenderPlan,formula_error_scan:'formula_error_scan.ndjson',visual_review_status:'awaiting human image inspection',
  csv_inputs:csvFiles,elapsed_seconds:(Date.now()-started)/1000};
await fs.writeFile(path.join(qaDir,'workbook_validation.json'),JSON.stringify(qa,null,2)+'\n');
console.log(JSON.stringify({output:outputPath,sheets:sheets.length,source_cells:inputCells.length,
  formula_cells:formulaChecks.length,charts:2,rendered_views:activeRenderPlan.length,qa:qaDir,elapsed_seconds:qa.elapsed_seconds},null,2));
