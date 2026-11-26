        import {workspace} from '../workspace.js';
        import {el} from '../dom.js';

        const page = {
  "title": "色样册干样点测",
  "module": "干样点测色样",
  "caption": "干样点测色样",
  "detail": "同底色不同配比的干样记录供回归估计。静置时间和凭证经二次复核后方能参与计算；抄错的色差可由复核员撤回点测凭证，补测验真后用新读数重算。",
  "path": "/dry_swatches",
  "columns": [
    {
      "name": "code",
      "label": "编号"
    },
    {
      "name": "family",
      "label": "色样册"
    },
    {
      "name": "fraction",
      "label": "调色比例"
    },
    {
      "name": "ground_l",
      "label": "底样 Lab 亮度"
    },
    {
      "name": "delta_e",
      "label": "干样与复制参考 ΔE76"
    },
    {
      "name": "sample_ref",
      "label": "点测凭证"
    },
    {
      "name": "dry_hours",
      "label": "静置小时"
    },
    {
      "name": "witnessed",
      "label": "已验真"
    },
    {
      "name": "state",
      "label": "凭证状态",
      "kind": "badge",
      "badgeMap": {"已撤回": "stale", "已验真": "ok", "待验真": "wait"}
    }
  ],
  "layout": "stack",
  "view": "table",
  "actions": [
    {
      "name": "record_swatch",
      "label": "登记干样点测",
      "path": "/dry_swatches/record-swatch",
      "fields": [
        {"name": "code", "label": "干样编号", "kind": "text", "initial": "SWATCH-QA"},
        {"name": "family", "label": "色样册", "kind": "text", "initial": "SAND-BATCH"},
        {"name": "fraction", "label": "调色比例", "kind": "float", "initial": 0.51},
        {"name": "ground_l", "label": "底样亮度 Lab L*", "kind": "float", "initial": 58.2},
        {"name": "delta_e", "label": "ΔE76", "kind": "float", "initial": 1.44},
        {"name": "sample_ref", "label": "点测凭证", "kind": "text", "initial": "COLOR-QA"},
        {"name": "dry_hours", "label": "静置小时", "kind": "int", "initial": 26}
      ],
      "help": "录入与复制参考片比较的已测 ΔE76。",
      "roles": ["operator", "reviewer"],
      "success": "已写入"
    },
    {
      "name": "witness_swatch",
      "label": "验真干样点测",
      "path": "/dry_swatches/witness-swatch",
      "fields": [
        {"name": "chip", "label": "干样编号", "kind": "text", "initial": "SWATCH-QA"}
      ],
      "help": "只有静置满一天且有凭证的数据可进入试色建议。",
      "roles": ["reviewer"],
      "success": "已写入"
    },
    {
      "name": "withdraw_ref",
      "label": "撤回凭证",
      "path": "/dry_swatches/withdraw-ref",
      "fields": [
        {"name": "sample_ref", "label": "点测凭证号（或填干样编号）", "kind": "text", "initial": "COLOR-QA"},
        {"name": "reason", "label": "撤回原因", "kind": "text", "initial": "干样色差抄录错误", "required": false}
      ],
      "help": "干样色差抄错时由复核员撤回点测凭证。撤回一经登记，排队到待签中凡训练或留出验证用过该凭证的预测一律失效（工作台标为待补测）；未用过它的预测仍可签认。",
      "roles": ["reviewer"],
      "success": "凭证已撤回"
    },
    {
      "name": "retest_swatch",
      "label": "补测验真",
      "path": "/dry_swatches/retest-swatch",
      "fields": [
        {"name": "chip", "label": "干样编号", "kind": "text", "initial": "SWATCH-QA"},
        {"name": "delta_e", "label": "补测 ΔE76 新读数", "kind": "float", "initial": 1.52},
        {"name": "dry_hours", "label": "静置小时", "kind": "int", "initial": 26},
        {"name": "witness", "label": "复核员直接验真", "kind": "bool", "initial": true}
      ],
      "help": "写入补测后的新读数；勾选验真可一步完成，否则再用“验真干样点测”。旧预测不会复活，须用新读数重新计算。",
      "roles": ["operator", "reviewer"],
      "success": "补测读数已写入"
    }
  ]
};

        export const {title} = page;
        export const key = "dry_swatches";
        export async function render(root, role) {
          await workspace(root, role, page);

        }
