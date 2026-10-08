const fs = require('fs');
const path = require('path');
const parserRoot = path.join(process.env.TEMP || process.env.TMP, 'healthflow-v5-php-parser', 'node_modules', 'php-parser');
const Engine = require(parserRoot);
const sqlParserRoot = path.join(process.env.TEMP || process.env.TMP, 'healthflow-v5-sql-parser', 'node_modules', 'node-sql-parser');
const SqlParser = require(sqlParserRoot).Parser;
const root = path.resolve(__dirname, '..');
const addonRoot = path.join(root, 'addons', 'shop');
const engine = new Engine({parser: {php7: true, suppressErrors: false}, ast: {withPositions: true}});

function walk(dir, result = []) {
  for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
    if (entry.name === 'uniapp' || entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, result);
    else if (entry.name.endsWith('.php')) result.push(full);
  }
  return result;
}

const errors = [];
for (const file of walk(addonRoot)) {
  try { engine.parseCode(fs.readFileSync(file, 'utf8'), file); }
  catch (error) { errors.push(`${path.relative(root, file)}: ${error.message}`); }
}

const schema = fs.readFileSync(path.join(addonRoot, 'database', 'v5_schema.sql'), 'utf8');
const installSchema = fs.readFileSync(path.join(addonRoot, 'install.sql'), 'utf8');
try {
  const parser = new SqlParser();
  for (const statement of schema.replace(/^\s*--.*$/gm, '').replaceAll('__PREFIX__', 'fa_').split(';').map(item => item.trim()).filter(Boolean)) {
    parser.astify(statement, {database: 'MySQL'});
  }
} catch (error) { errors.push(`MySQL schema parse failed: ${error.message}`); }
const tables = [...schema.matchAll(/CREATE TABLE IF NOT EXISTS\s+`__PREFIX__([^`]+)`/g)].map(match => match[1]);
const duplicates = tables.filter((name, index) => tables.indexOf(name) !== index);
if (duplicates.length) errors.push(`duplicate V5 tables: ${[...new Set(duplicates)].join(', ')}`);
for (const match of schema.matchAll(/CREATE TABLE IF NOT EXISTS\s+`__PREFIX__([^`]+)`\s*\(([\s\S]*?)\)\s*ENGINE=/g)) {
  const columns = [...match[2].matchAll(/^\s*`([^`]+)`\s+/gm)].map(item => item[1]);
  const repeated = columns.filter((name, index) => columns.indexOf(name) !== index);
  if (repeated.length) errors.push(`duplicate columns in ${match[1]}: ${[...new Set(repeated)].join(', ')}`);
}

function schemaColumns(sql, result = new Map()) {
  for (const match of sql.matchAll(/CREATE TABLE IF NOT EXISTS\s+`__PREFIX__([^`]+)`\s*\(([\s\S]*?)\)\s*ENGINE\s*=/g)) {
    if (!result.has(match[1])) result.set(match[1], new Set());
    for (const column of match[2].matchAll(/^\s*`([^`]+)`\s+/gm)) result.get(match[1]).add(column[1]);
  }
  return result;
}

const knownColumns = schemaColumns(installSchema);
schemaColumns(schema, knownColumns);
const coreColumns = {
  user: ['id','username','nickname','mobile','level','score','money','jointime','status'],
  auth_group: ['id','pid','name','rules','status','createtime','updatetime'],
  admin_log: ['id','admin_id','username','url','title','content','ip','useragent','createtime'],
};
for (const [table, columns] of Object.entries(coreColumns)) knownColumns.set(table, new Set(columns));
const migrator = fs.readFileSync(path.join(addonRoot, 'library', 'v5', 'Migrator.php'), 'utf8');
const columnSection = migrator.slice(migrator.indexOf('$columns = ['), migrator.indexOf('$indexes = ['));
for (const block of columnSection.matchAll(/^\s*'([^']+)'\s*=>\s*\[([\s\S]*?)^\s*\],/gm)) {
  if (!knownColumns.has(block[1])) knownColumns.set(block[1], new Set());
  for (const field of block[2].matchAll(/^\s*'([^']+)'\s*=>/gm)) knownColumns.get(block[1]).add(field[1]);
}

const workspace = fs.readFileSync(path.join(addonRoot, 'application', 'admin', 'controller', 'shop', 'v5', 'Workspace.php'), 'utf8');
const virtualFields = new Set([
  'shop_supplier.secret_configured', 'shop_supplier.secret_plaintext',
  'shop_integration_client.secret_configured', 'shop_integration_client.secret_plaintext',
]);
for (const line of workspace.split(/\r?\n/)) {
  const resource = line.match(/^\s*'[^']+'\s*=>\s*\$this->r\('([^']+)',\s*\[([^\]]*)\],\s*\[([^\]]*)\]/);
  if (!resource) continue;
  const table = resource[1];
  const available = knownColumns.get(table);
  if (!available) {
    errors.push(`workspace table is not declared: ${table}`);
    continue;
  }
  const displayed = [...resource[2].matchAll(/'([^']+)'\s*=>/g)].map(item => item[1]);
  const searched = [...resource[3].matchAll(/'([^']+)'/g)].map(item => item[1]);
  const editable = [...line.matchAll(/'([^']+)'\s*=>\s*\$this->f\(/g)].map(item => item[1]);
  for (const field of [...displayed, ...searched, ...editable]) {
    if (!available.has(field) && !virtualFields.has(`${table}.${field}`)) errors.push(`workspace field missing: ${table}.${field}`);
  }
}

const menu = fs.readFileSync(path.join(addonRoot, 'data', 'menu.php'), 'utf8');
const roots = ['shop/v5/workspace/dashboard', 'shop_v5_catalog', 'shop_v5_orders', 'shop_v5_supply', 'shop_v5_operations'];
for (const name of roots) if (!menu.includes(`'name' => '${name}'`)) errors.push(`missing menu root: ${name}`);
const visibleWorkspaceEntries = [...menu.matchAll(/'name' => 'shop\/v5\/workspace\/(product|ingredients|recommendations|plans|purchases|orders|batches|fulfillment|aftersales|suppliers|supplier_sku|supplier_collaboration|delivery_rules|analytics|marketing|members|settings|audit)'[^\n]*'ismenu' => 1/g)];
if (visibleWorkspaceEntries.length !== 18) errors.push(`visible workspace entries: expected 18, got ${visibleWorkspaceEntries.length}`);

const shop = fs.readFileSync(path.join(addonRoot, 'Shop.php'), 'utf8');
const routes = [...shop.matchAll(/'addons\/shop\/api\.v1\.([a-z_]+)\/([A-Za-z0-9_]+)'/g)];
const routeRules = [...shop.matchAll(/\['([^']+)',\s*'addons\/shop\/api\.v1\.[^']+',\s*'([^']+)'\]/g)].map(match => `${match[2]} ${match[1]}`);
const duplicateRoutes = routeRules.filter((name, index) => routeRules.indexOf(name) !== index);
if (duplicateRoutes.length) errors.push(`duplicate routes: ${[...new Set(duplicateRoutes)].join(', ')}`);
for (const [, controller, action] of routes) {
  const className = controller.split('_').map(part => part[0].toUpperCase() + part.slice(1)).join('');
  const file = path.join(addonRoot, 'controller', 'api', 'v1', `${className}.php`);
  if (!fs.existsSync(file)) errors.push(`route controller missing: ${className}`);
  else if (!new RegExp(`function\\s+${action}\\s*\\(`).test(fs.readFileSync(file, 'utf8'))) errors.push(`route action missing: ${className}::${action}`);
}

if (errors.length) {
  console.error(errors.join('\n'));
  process.exit(1);
}
console.log(`OK: ${walk(addonRoot).length} addon PHP files parsed; ${tables.length} V5 tables; 5 menu roots; 18 visible entries; ${routes.length} V1 routes.`);
