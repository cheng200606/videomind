// 生成状态变体页面：把构造函数里的初始 state 替换掉，得到某个交互状态的静态页
import fs from 'node:fs';
import path from 'node:path';
const dir = process.argv[2];
const rd = (f) => fs.readFileSync(path.join(dir, f), 'utf8');
const wr = (f, s) => fs.writeFileSync(path.join(dir, f), s);

const wb = rd('Workbench.dc.html');
const wbRe = /this\.state = \{ t: ev \? 1120 : 242,[^\n]*\};/;
if (!wbRe.test(wb)) throw new Error('workbench state line not found');
const W = {
  'WbJump': "{ t: 910, tab: 'sum', left: 'out', drawer: null, onlyPit: false, toast: '' }",
  'WbPts': "{ t: 910, tab: 'pts', left: 'out', drawer: null, onlyPit: false, toast: '' }",
  'WbUml': "{ t: 910, tab: 'uml', left: 'out', drawer: null, onlyPit: false, toast: '' }",
  'WbUmlJump': "{ t: 1290, tab: 'uml', left: 'out', drawer: null, onlyPit: false, toast: '已跳到 21:30 · computed 与 watch' }",
  'WbCode': "{ t: 1162, tab: 'code', left: 'out', drawer: null, onlyPit: false, toast: '' }",
  'WbEv': "{ t: 1120, tab: 'pts', left: 'out', drawer: 'k3', onlyPit: false, toast: '' }"
};
for (const [k, v] of Object.entries(W)) wr(k + '.dc.html', wb.replace(wbRe, 'this.state = ' + v + ';'));

const um = rd('P06Uml.dc.html');
const umRe = /this\.state = \{ kind: 'use', sel: 'u2' \};/;
if (!umRe.test(um)) throw new Error('uml state not found');
for (const [k, v] of Object.entries({ UmlClass: "{ kind: 'class', sel: 'c3' }", UmlSeq: "{ kind: 'seq', sel: 'm2' }", UmlFlow: "{ kind: 'flow', sel: 'f3' }" }))
  wr(k + '.dc.html', um.replace(umRe, 'this.state = ' + v + ';'));

const se = rd('P08Search.dc.html');
const seRe = /this\.state = \{ conf: 'all', drawer: null, handled: \[\] \};/;
if (!seRe.test(se)) throw new Error('search state not found');
wr('SearchSug.dc.html', se.replace(seRe, "this.state = { conf: 'all', drawer: 'sug', handled: [] };"));
console.log('variants ok');
