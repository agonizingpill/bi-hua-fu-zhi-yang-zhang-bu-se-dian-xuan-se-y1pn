import {request} from './api.js';
import {el} from './dom.js';
import {badge, status} from './widgets.js';

function shortToken(token) {
  return token ? token.slice(0, 12) : '—';
}

function headRow() {
  return el('tr', {},
    el('th', {scope: 'col'}, '拟合凭证'),
    el('th', {scope: 'col'}, '流程状态'),
    el('th', {scope: 'col'}, '工作台标记'),
    el('th', {scope: 'col'}, '被撤回凭证'),
    el('th', {scope: 'col'}, '签认簿'));
}

function jobRow(j) {
  return el('tr', {class: j.retest_required ? 'row-stale' : ''},
    el('td', {title: j.token || ''}, shortToken(j.token)),
    el('td', {}, j.state_label || j.status || '—'),
    el('td', {class: 'cell-badge'}, j.retest_required ? badge('待补测') : badge(j.state_label || j.status)),
    el('td', {}, (j.withdrawn_refs || []).join('、') || '—'),
    el('td', {}, j.confirmed_code || (j.confirmed ? '已签认' : '—')));
}

export function predictionsPanel() {
  const body = el('div', {class: 'scroll predictions-body'}, status('正在读取拟合任务…'));
  const refreshButton = el('button', {type: 'button', class: 'quiet refresh'}, '刷新');
  const heading = el('div', {class: 'predictions-head'},
    el('h2', {}, '拟合预测与待补测标记'), refreshButton);
  const section = el('section', {class: 'predictions ledger', 'aria-label': '拟合预测工作台'},
    heading, body);

  async function load() {
    try {
      const jobs = await request('/compute');
      if (!jobs.length) {
        body.replaceChildren(status('暂无拟合预测。提交“计算指定点试色建议”后，从排队到待签的任务会在这里标注凭证有效性。'));
        return;
      }
      const pending = jobs.filter(j => j.retest_required || j.invalid).length;
      const table = el('table', {},
        el('thead', {}, headRow()),
        el('tbody', {}, ...jobs.map(jobRow)));
      const notice = pending
        ? status(`${pending} 条预测因凭证撤回而失效，标记为待补测；请补测验真后用新读数重算。`, 'error')
        : null;
      body.replaceChildren(...[notice, table].filter(Boolean));
    } catch (error) {
      body.replaceChildren(status(error.message, 'error'));
    }
  }
  refreshButton.addEventListener('click', load);
  window.addEventListener('compute-changed', load);
  load();
  const timer = setInterval(() => {
    if (document.contains(section)) load();
    else clearInterval(timer);
  }, 4000);
  return section;
}
