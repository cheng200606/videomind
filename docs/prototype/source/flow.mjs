// 生成单文件可点击原型：每屏一张导出图 + 透明 # 热区，墨刀「HTML 转墨刀」会按 # 生成页面并连好跳转
// 用法：node flow.mjs <exportsDir> <out.html>
import fs from 'node:fs';
import path from 'node:path';
const [dir, out] = process.argv.slice(2);

const P = {
  home: { id: '', file: 'p00-cover@2x.png' },
  p01: { id: '01-视频库首页', file: 'p01-library@2x.png' },
  p02: { id: '02-批量上传', file: 'p02-upload@2x.png' },
  p03: { id: '03-批次进度', file: 'p03-progress@2x.png' },
  p04: { id: '04-知识工作台', file: 'p04-workbench@2x.png' },
  p04b: { id: '04b-播放头跳到1510', file: 'states/p04b-jump@2x.png' },
  p04c: { id: '04c-要点面板', file: 'states/p04c-points@2x.png' },
  p04d: { id: '04d-UML面板', file: 'states/p04d-uml@2x.png' },
  p04e: { id: '04e-点UML节点后', file: 'states/p04e-uml-jump@2x.png' },
  p04f: { id: '04f-代码块面板', file: 'states/p04f-code@2x.png' },
  p05: { id: '05-证据链', file: 'p05-evidence@2x.png' },
  p06: { id: '06-UML用例图', file: 'p06-uml@2x.png' },
  p06b: { id: '06b-UML类图', file: 'states/p06b-class@2x.png' },
  p06c: { id: '06c-UML时序图', file: 'states/p06c-seq@2x.png' },
  p06d: { id: '06d-UML流程图', file: 'states/p06d-flow@2x.png' },
  p07: { id: '07-笔记编辑', file: 'p07-notes@2x.png' },
  p08: { id: '08-标签与检索', file: 'p08-search@2x.png' },
  p08b: { id: '08b-AI标签建议', file: 'states/p08b-suggest@2x.png' },
  p09: { id: '09-导出', file: 'p09-export@2x.png' },
  p10: { id: '10-批次后台', file: 'p10-admin@2x.png' },
  p11: { id: '11-设置', file: 'p11-settings@2x.png' },
  p12: { id: '12-异常态', file: 'p12-errors@2x.png' }
};
// 热区：[x, y, w, h, 目标]，坐标为 1440 设计宽下的 CSS 像素
const NAV = [[60, 0, 46, 48, 'home'], [118, 0, 56, 48, 'p01'], [184, 0, 70, 48, 'p02'], [262, 0, 72, 48, 'p08'], [1260, 0, 68, 48, 'p10'], [1336, 0, 44, 48, 'p11']];
const CRUMB_WB = [[62, 66, 44, 26, 'p01'], [110, 66, 132, 26, 'p03']];
const WB_TABS = [[952, 412, 36, 36, 'p04'], [998, 412, 50, 36, 'p04c'], [1060, 412, 40, 36, 'p04d'], [1110, 412, 54, 36, 'p04f']];
const WB_COMMON = [...NAV, ...CRUMB_WB, ...WB_TABS,
  [912, 330, 38, 38, 'p05'],            // 刻度尺 3 号圆标 → 证据链
  [766, 241, 290, 30, 'p04b'],          // 章节色块「解构陷阱」→ 播放头跳转
  [62, 636, 316, 58, 'p04b'],           // 大纲 15:10 → 播放头跳转
  [62, 514, 316, 58, 'p04'],            // 大纲 03:20 → 回到 ref 章节
  [862, 735, 72, 36, 'p04']             // 记笔记按钮占位，下面单独覆盖
];
const H = {
  home: [[62, 556, 314, 64, 'p02'], [396, 556, 314, 64, 'p03'], [730, 556, 314, 64, 'p04'], [1064, 556, 314, 64, 'p05'],
         [62, 626, 314, 64, 'p09'], [396, 626, 314, 64, 'p01'], [730, 626, 314, 64, 'p08'], [1064, 626, 314, 64, 'p07'],
         [62, 695, 314, 64, 'p06'], [396, 695, 314, 64, 'p11'], [730, 695, 314, 64, 'p10'], [1064, 695, 314, 64, 'p12']],
  p01: [...NAV, [1270, 172, 108, 52, 'p02'], [62, 336, 222, 30, 'p03'], [62, 430, 30, 22, 'p03'], [100, 430, 30, 22, 'p09'],
        [396, 380, 982, 36, 'p04'], [396, 418, 982, 36, 'p04'], [396, 455, 982, 36, 'p04']],
  p02: [...NAV, [953, 632, 425, 50, 'p03'], [953, 588, 58, 22, 'p11']],
  p03: [...NAV, [62, 66, 44, 26, 'p01'], [1064, 159, 314, 47, 'p04'], [1064, 212, 314, 47, 'p09'],
        [1294, 625, 84, 37, 'p04'], [1294, 698, 84, 37, 'p04'], [1294, 772, 84, 37, 'p04'], [1294, 478, 84, 37, 'p12']],
  p04: [...WB_COMMON, [966, 773, 86, 38, 'p05'], [862, 735, 72, 36, 'p07']],
  p04b: [...WB_COMMON, [966, 773, 86, 38, 'p05'], [862, 735, 72, 36, 'p07']],
  p04c: [...WB_COMMON, [862, 735, 72, 36, 'p07']],
  p04d: [...WB_COMMON, [953, 498, 425, 42, 'p04'], [953, 552, 425, 42, 'p04'], [953, 606, 425, 42, 'p04b'], [953, 660, 425, 42, 'p04e'],
         [953, 712, 112, 26, 'p06'], [862, 735, 72, 36, 'p07']],
  p04e: [...WB_COMMON, [953, 498, 425, 42, 'p04'], [953, 552, 425, 42, 'p04'], [953, 606, 425, 42, 'p04b'], [953, 660, 425, 42, 'p04e'],
         [953, 712, 112, 26, 'p06'], [862, 735, 72, 36, 'p07']],
  p04f: [...WB_COMMON, [862, 735, 72, 36, 'p07']],
  p05: [[1356, 5, 58, 38, 'p04'], [966, 385, 118, 37, 'p04b'], [1304, 751, 110, 38, 'p07'], [0, 0, 938, 1000, 'p04']],
  p06: [], p06b: [], p06c: [], p06d: [],
  p07: [...NAV, [62, 66, 44, 26, 'p01'], [110, 66, 150, 26, 'p04'], [459, 170, 40, 22, 'p04']],
  p08: [...NAV, [1064, 214, 314, 47, 'p08b'], [62, 282, 982, 80, 'p04'], [62, 388, 982, 80, 'p04'], [62, 494, 982, 80, 'p04'], [62, 600, 982, 80, 'p04']],
  p08b: [[1352, 5, 62, 38, 'p08'], [0, 0, 990, 1000, 'p08']],
  p09: [...NAV, [62, 66, 44, 26, 'p01'], [110, 66, 128, 26, 'p03'], [587, 300, 48, 24, 'p03'], [1308, 363, 70, 24, 'p07']],
  p10: [...NAV, [1336, 450, 30, 26, 'p03'], [1336, 561, 30, 26, 'p03'], [1336, 616, 30, 26, 'p03'], [1260, 500, 106, 36, 'p03'], [1260, 666, 106, 36, 'p03']],
  p11: [...NAV],
  p12: [...NAV, [953, 443, 144, 44, 'p09'], [1102, 443, 130, 44, 'p03'], [507, 451, 90, 44, 'p04'], [601, 451, 130, 44, 'p11']]
};
const UML = [...NAV, [62, 66, 44, 26, 'p01'], [110, 66, 150, 26, 'p04'], [62, 112, 84, 50, 'p06'], [175, 112, 42, 50, 'p06b'],
             [246, 112, 84, 50, 'p06c'], [358, 112, 84, 50, 'p06d'], [953, 398, 174, 47, 'p04b']];
for (const k of ['p06', 'p06b', 'p06c', 'p06d']) H[k] = UML;

// 墨刀图床上已有的同一批图（按上传顺序核对过尺寸）；传第 5 个参数 url 时改用远程地址，文件只剩几十 KB
const BASE = 'https://modao.cc/uploads7/images/18701/';
const URLS = { p04: '187016999/v2_tou5hi', home: '187017007/v2_tou5l4', p01: '187017018/v2_tou5pd', p02: '187017021/v2_tou5qw',
  p03: '187017024/v2_tou5rw', p05: '187017030/v2_tou5t9', p06: '187017033/v2_tou5u9', p07: '187017049/v2_tou5vf',
  p08: '187017053/v2_tou5wh', p09: '187017061/v2_tou5xp', p10: '187017066/v2_tou5yq', p11: '187017071/v2_tou5zs',
  p12: '187017074/v2_tou60w', p04b: '187017076/v2_tou622', p04c: '187017078/v2_tou638', p04d: '187017081/v2_tou64d',
  p04e: '187017084/v2_tou65o', p04f: '187017088/v2_tou66z', p06b: '187017090/v2_tou67v', p06c: '187017092/v2_tou68u',
  p06d: '187017095/v2_tou69q', p08b: '187017105/v2_tou6ar' };
const useUrl = process.argv[5] === 'url';
const size = (buf) => [Math.round(buf.readUInt32BE(16) / 2), Math.round(buf.readUInt32BE(20) / 2)];
const href = (k) => '#' + P[k].id;
let css = 'html,body{margin:0}body{position:relative;width:1440px;overflow:hidden}section{display:none;position:absolute;left:0;top:0;width:1440px}' +
  'section img{display:block;width:1440px}a.h{position:absolute;display:block}section:target{display:block}' +
  'body:not(:has(section:target)) #home{display:block}';
let html = '';
for (const [k, p] of Object.entries(P)) {
  const buf = fs.readFileSync(path.join(dir, p.file));
  const [w, h] = size(buf);
  const sel = k === 'home' ? 'body:not(:has(section:target))' : `body:has([id="${p.id}"]:target)`;
  css += `${sel}{height:${h}px}`;
  const links = (H[k] || []).filter((l) => l[4] !== k || k === 'p04').map(([x, y, lw, lh, t]) =>
    `<a class="h" href="${href(t)}" style="left:${x}px;top:${y}px;width:${lw}px;height:${lh}px"></a>`).join('');
  html += `<section id="${k === 'home' ? 'home' : p.id}" style="height:${h}px"><img alt="${p.id || '00-封面'}" src="${useUrl ? BASE + URLS[k] + '.png' : 'data:image/png;base64,' + buf.toString('base64')}" style="height:${h}px">${links}</section>\n`;
}
if (process.argv[4] === 'debug') css += 'a.h{outline:3px solid rgba(0,160,255,.9);background:rgba(0,160,255,.15)}';
fs.mkdirSync(path.dirname(out), { recursive: true });
const doc = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>视析</title><style>${css}</style></head><body>\n${html}</body></html>`;
fs.writeFileSync(out, doc);
console.log('pages', Object.keys(P).length, 'size', (doc.length / 1024 / 1024).toFixed(2) + ' MB');
