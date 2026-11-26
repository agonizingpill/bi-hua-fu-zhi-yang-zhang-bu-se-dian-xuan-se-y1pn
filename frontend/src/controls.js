import {awaitCompute, request} from './api.js';
import {el, display} from './dom.js';
import {COMPUTE_STATES, evidence} from './store.js';
import {status} from './widgets.js';

const fallback = field => field.kind === 'token' ? evidence.get() : field.initial;
function input(field) {
  const required = field.required === false ? undefined : '';
  if (field.kind === 'bool') return el('select', {name:field.name},
    el('option',{value:'true', selected:fallback(field) === true ? '' : undefined},'是'),
    el('option',{value:'false', selected:fallback(field) === false ? '' : undefined},'否'));
  if (field.kind === 'json') return el('textarea', {name:field.name, required:''}, JSON.stringify(fallback(field), null, 2));
  if (field.kind === 'textarea') return el('textarea', {name:field.name, required}, fallback(field) ?? '');
  const numeric = ['int','float'].includes(field.kind);
  return el('input',{name:field.name, required, type:numeric ? 'number' : 'text',
    step:field.kind === 'float' ? 'any' : undefined, value:fallback(field) ?? ''});
}
function parse(form, fields) {
  const data = new FormData(form);
  return Object.fromEntries(fields.map(field => {
    const raw = data.get(field.name);
    const convert = ['int','float'].includes(field.kind) ? Number :
      ['bool','json'].includes(field.kind) ? JSON.parse : String;
    return [field.name, convert(raw)];
  }));
}
export function actionForm(action, refresh) {
  const notice = status('');
  const button = el('button', {type:'submit'}, action.label);
  const form = el('form', {class:'action', id:action.name},
    el('h3',{},action.label), el('p',{},action.help),
    el('div',{class:'fields'},action.fields.map(field => el('label',{},
      el('span',{},field.label + (field.required === false ? '（选填）' : '')), input(field)))),
    button, notice);
  form.addEventListener('submit',async event => {
    event.preventDefault();
    button.disabled = true;
    notice.className = 'status';
    try {
      const data = await request(action.path, parse(form, action.fields));
      if (data.token && data.status === 'queued') {
        evidence.save(data.token);
        const result = await awaitCompute(data.token, current => {
          notice.textContent = current.retest_required || current.invalid
            ? '待补测：该预测引用的凭证已撤回，预测失效'
            : (COMPUTE_STATES[current.status] || current.status);
        });
        if (result.status === 'rejected') throw new Error(result.detail);
        await refresh();
        window.dispatchEvent(new window.CustomEvent('compute-changed'));
        if (result.retest_required || result.invalid) {
          notice.textContent = '凭证已撤回，本预测自排队起即失效，工作台已标为待补测；请补测验真后用新读数重算，再用新拟合凭证签认。';
          notice.classList.add('error');
          return;
        }
        notice.textContent = '任务 ' + data.token + ' · ' + display(result.result);
      } else {
        notice.textContent = action.success + ' · ' + display(data.code ?? data.status);
      }
      notice.classList.add('ok');
      await refresh();
      window.dispatchEvent(new window.CustomEvent('compute-changed'));
    } catch (error) {
      notice.textContent = error.message;
      notice.classList.add('error');
      window.dispatchEvent(new window.CustomEvent('compute-changed'));
    } finally { button.disabled = false; }
  });
  return form;
}
