# 扩展钩子（宿主系统集成）

构建产物（`out/<study>/HTML/`）可被宿主系统（如康哲医学经理工作台 mm3）在不修改 skill 的前提下挂接额外层。
**一切在构建时声明，运行时零探测**——`fetch`/`HEAD` 在 `file://` 下不可用且缺资源加载会写 console error
（会被 `render_check.js` 判失败），因此不用任何运行时存在性探测。

## 声明方式

`study.json` 的 `cfg.ext`：

```json
{"cfg": {"ext": {"sys": "data/sys.js",
                 "js": ["assets/ext/kz-sys.js"],
                 "css": ["assets/ext/kz-sys.css"]}}}
```

`templates/site/assets/kz.js` 末尾的加载器在每页读取 `window.KZ.cfg.ext`（`data/core.js` 先于 `kz.js` 加载），
按清单注入 `<link>`/`<script>`（`async=false`，保序）。清单里声明的文件由宿主在构建产物中提供。

- `sys`：系统层数据（约定为 `data/sys.js` → `window.KZS`，见下）；与其他 js 一样按声明加载。
- 不写 `cfg.ext`（skill 单独使用）→ 加载器直接返回，页面行为与无此钩子完全一致。

## 约定：`window.KZS`

宿主写入 `data/sys.js`：`window.KZS = {project, snapshot, build, mode, thresholds, diff, qstate, csb, final, qc}`。
字段可缺省，系统层脚本须对缺省字段安全降级。skill 模板本身**不读取** `KZS`——展示逻辑由宿主提供的
`assets/ext/*.js` 完成（如总览项目信息条）；skill 页面与数据契约不变。

## 宿主侧注意

- `cfg.ext` 声明的文件必须随产物存在，否则页面 console 报资源加载失败（render_check 判红）。
- 离线（`file://`）与静态导出均适用；宿主静态导出时可把 `sys.js` 写为只读快照。
- 构建指纹不写在扩展层：宿主把指纹追加进 `cfg.footer.right`（skill 页脚原样渲染）。
