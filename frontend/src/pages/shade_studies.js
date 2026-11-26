        import {workspace} from '../workspace.js';
        import {el} from '../dom.js';
        import {badge} from '../widgets.js';
        import {predictionsPanel} from '../predictions.js';

        function readingHead() {
          return el('tr', {},
            el('th', {scope: 'col'}, '干样编号'),
            el('th', {scope: 'col'}, '点测凭证'),
            el('th', {scope: 'col'}, '比例'),
            el('th', {scope: 'col'}, '底样 L*'),
            el('th', {scope: 'col'}, 'ΔE76 原值'));
        }
        function readingRow(r) {
          return el('tr', {},
            el('td', {}, r.code || '—'),
            el('td', {}, r.sample_ref || '—'),
            el('td', {}, r.fraction ?? '—'),
            el('td', {}, r.ground_l ?? '—'),
            el('td', {}, r.delta_e ?? '—'));
        }
        function readingsTable(row) {
          const readings = row.readings || [];
          if (!readings.length) return null;
          return el('div', {class: 'scroll snapshot-scroll'},
            el('table', {class: 'snapshot-table'},
              el('thead', {}, readingHead()),
              el('tbody', {}, ...readings.map(readingRow))));
        }

        const page = {
  "title": "Gaussian Process 色差与区间",
  "module": "色差区间签认",
  "caption": "色差区间签认",
  "detail": "以底样亮度和试色比例估计复制样张色差。模型返回候选均值与区间，审核签认后方可占用试色位；签认时固化所用干样读数与区间，凭证事后撤回仍可在工作台查原值。",
  "path": "/shade_studies",
  "columns": [
    {"name": "code", "label": "编号"},
    {"name": "panel", "label": "样张"},
    {"name": "revision", "label": "连续边界版次"},
    {"name": "x_mm", "label": "补色点 X"},
    {"name": "y_mm", "label": "补色点 Y"},
    {"name": "ground_l", "label": "样张底色亮度"},
    {"name": "fraction", "label": "建议调色比例"},
    {"name": "mean_de", "label": "预测 ΔE76"},
    {"name": "lower_de", "label": "95% 区间下端"},
    {"name": "upper_de", "label": "95% 区间上端"},
    {"name": "interval_text", "label": "签认区间快照"},
    {"name": "reading_count", "label": "固化干样读数条数"},
    {"name": "test_mae", "label": "留出格 MAE"},
    {"name": "token", "label": "拟合凭证"}
  ],
  "layout": "flip",
  "view": "grid",
  rowHeading(row) {
    const kids = [];
    if ((row.subsequent_withdrawn_refs || []).length) {
      kids.push(el('p', {class:'snapshot-note'},
        badge('凭证事后撤回'),
        el('span', {}, ' 签认快照保留原值：' + row.subsequent_withdrawn_refs.join('、'))));
    }
    return kids.length ? el('div', {class:'row-flags'}, ...kids) : null;
  },
  rowExtra(row) {
    if (!(row.readings || []).length) return null;
    return el('details', {class:'snapshot'},
      el('summary', {}, `签认干样读数与区间快照（${row.reading_count} 条 · 区间 ${row.interval_text || ''}）`),
      readingsTable(row));
  },
  "actions": [
    {
      "name": "fit_at_point",
      "label": "计算指定点试色建议",
      "path": "/shade_studies/fit-at-point",
      "fields": [
        {"name": "panel", "label": "样张编号", "kind": "text", "initial": "PANEL-W8"},
        {"name": "x_mm", "label": "补色点 X", "kind": "int", "initial": 32},
        {"name": "y_mm", "label": "补色点 Y", "kind": "int", "initial": 21},
        {"name": "ground_l", "label": "点位底色 Lab L*", "kind": "float", "initial": 58}
      ],
      "help": "量化不确定性，候选在干样配比范围内搜索。所用凭证被撤回时，任务会在下方预测工作台标为待补测。",
      "roles": ["operator", "reviewer"],
      "success": "已写入"
    },
    {
      "name": "confirm_color",
      "label": "签认拟合与不确定区间",
      "path": "/shade_studies/confirm-color",
      "fields": [
        {"name": "code", "label": "签认簿号", "kind": "text", "initial": "COLOR-QA"},
        {"name": "token", "label": "拟合凭证", "kind": "token", "initial": ""}
      ],
      "help": "固化当次训练/留出所用干样读数、区间、点位坐标和边界修订号；引用已撤回凭证的旧预测会被挡住。",
      "roles": ["reviewer"],
      "success": "已写入"
    }
  ]
};

        export const {title} = page;
        export const key = "shade_studies";
        export async function render(root, role) {
          await workspace(root, role, page);
          root.appendChild(predictionsPanel());
        }
