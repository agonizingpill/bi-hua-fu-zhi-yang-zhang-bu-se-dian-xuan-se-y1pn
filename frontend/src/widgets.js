import {display, el} from './dom.js';

export function status(message, variant = '') {
  return el('p', {class:'status ' + variant, role:'status'}, message);
}
export function dataView(rows, columns, layout, page) {
  if (!rows.length) return status('暂无可用记录。可先填入一条领域凭证。');
  if (layout === 'table') {
    return el('div', {class:'scroll'}, el('table', {},
      el('thead', {}, el('tr', {}, columns.map(x => el('th', {scope:'col'}, x.label)))),
      el('tbody', {}, rows.map(r => el('tr', {}, columns.map(x => el('td', {class:x.kind === 'badge' ? 'cell-badge' : ''},
        x.kind === 'badge' ? badge(r[x.name], x.badgeMap) : display(r[x.name]))))))));
  }
  return el('div', {class:'records ' + layout}, rows.map(row =>
    el('article', {class:'record' + (row._pending ? ' pending-retest' : '')},
      el('h3',{},display(row[columns[0].name])),
      page && page.rowHeading ? page.rowHeading(row) : null,
      el('dl',{},columns.slice(1).flatMap(x => [
        el('dt',{},x.label), el('dd',{}, x.kind === 'badge' ? badge(row[x.name], x.badgeMap) : display(row[x.name]))])),
      page && page.rowExtra ? page.rowExtra(row) : null)));
}

export function badge(value, map) {
  const text = value === true ? '待补测' : (value || '');
  if (!text) return document.createTextNode('—');
  let tone = 'wait';
  if (map && map[text]) tone = map[text];
  else if (String(text).includes('待补测') || String(text).includes('撤回') || String(text).includes('失效')) tone = 'stale';
  else if (String(text).includes('已签认') || String(text).includes('已验真') || String(text).includes('有效')) tone = 'ok';
  return el('span', {class:'badge ' + tone}, String(text));
}

export function titleBlock(kicker, title, detail) {
  return el('header', {class:'title'}, el('span', {class:'kicker'}, kicker), el('h1', {}, title),
    el('p', {class:'intro'}, detail));
}
