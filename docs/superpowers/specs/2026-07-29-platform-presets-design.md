# 平台预设增强设计

## 背景

客户使用问题归因智能体已经支持海外电商客服会话的单条分析、文件上传、批量分析、人工复核、记录筛选、详情展开、运营概览和 CSV 导出。当前粘贴、单文件上传和批量上传表单里的“平台来源”都是普通文本框，默认值为 `Other overseas platform`。

这种方式足够灵活，但容易出现同一平台的多种写法，例如 `tiktok`、`TikTokShop`、`TikTok Shop`，后续筛选、概览和 CSV 复盘时会产生不必要的分散。用户之前也明确说明平台不仅有 Amazon 和 TikTok，还有其他海外电商平台，因此本轮目标是提升录入一致性，同时保留开放输入。

## 目标

- 为三个平台来源输入框增加常用海外电商平台预设。
- 使用 HTML `datalist`，不把输入限制为白名单。
- 覆盖 Amazon、TikTok Shop、Shopee、Walmart Marketplace、eBay、Shopify、AliExpress、Lazada、Temu、Shein、Other overseas platform。
- 保持后端仍按字符串保存平台来源。
- 保持最近记录筛选、CSV 平台过滤和运营概览既有行为。
- README 说明用户可以选择预设，也可以输入其他海外电商平台名称。

## 非目标

- 不做平台账号绑定。
- 不做平台 API 同步。
- 不做平台专属解析模板。
- 不做平台字段枚举迁移。
- 不做多语言平台名标准化。
- 不改变历史记录平台字段。
- 不调用模型，不增加供应商请求。

## 推荐方案

在首页模板中新增一个共享 `<datalist id="platform-presets">`，并给 `paste-platform`、`upload-platform`、`batch-platform` 三个输入框增加 `list="platform-presets"`。浏览器会提供预设建议，但用户仍能输入任意字符串。

这个方案最轻、风险最低，也符合现有后端接口：三个分析接口已经接收 `platform: str`，存储层和导出层也只把平台当作普通字符串。我们不需要新增 API、JavaScript 或数据库迁移。

## 备选方案

方案 A：把平台输入改成 `<select>`。这种方式能强制统一，但会排除未列出的海外平台，违背“还有其他海外电商平台”的要求，因此不采用。

方案 B：新增“平台选择 + 自定义平台”两个字段。语义更强，但表单更复杂，还需要前端合并字段值。当前 `datalist` 已能同时满足预设和自由输入，因此不采用。

方案 C：后端做平台别名标准化。长期有价值，但会改变数据语义，并需要维护映射表和历史兼容策略，不适合本轮轻量增强。

## UI 设计

三个表单保持现有布局和标签：

- 粘贴会话：`#paste-platform`
- 上传文件：`#upload-platform`
- 批量上传：`#batch-platform`

每个输入框增加：

```html
list="platform-presets"
```

在页面中放置一次共享预设：

```html
<datalist id="platform-presets">
  <option value="Amazon"></option>
  <option value="TikTok Shop"></option>
  <option value="Shopee"></option>
  <option value="Walmart Marketplace"></option>
  <option value="eBay"></option>
  <option value="Shopify"></option>
  <option value="AliExpress"></option>
  <option value="Lazada"></option>
  <option value="Temu"></option>
  <option value="Shein"></option>
  <option value="Other overseas platform"></option>
</datalist>
```

默认值继续使用 `Other overseas platform`，避免改变现有空白表单体验。

## 数据流

用户选择预设或手动输入平台名称后，表单仍提交 `platform` 字段。FastAPI、分析请求对象、JSONL 存储、最近记录、CSV 导出和筛选功能都继续读取同一个字符串字段。

## 错误处理

- 用户手动输入未出现在预设中的平台：正常提交和保存。
- 用户清空平台：沿用现有后端校验和默认行为。
- 浏览器不支持 `datalist`：输入框仍作为普通文本框工作。

## 测试策略

- 首页 HTML 测试覆盖 `platform-presets` datalist 存在。
- 首页 HTML 测试覆盖三个平台输入框都绑定 `list="platform-presets"`。
- 首页 HTML 测试覆盖关键平台预设值。
- 回归测试确认自定义平台仍能通过分析接口保存。
- 全量测试确认现有分析、上传、批量、筛选、导出、概览和详情功能不受影响。

## 验收标准

- 用户在三个平台输入框中都能看到常用平台预设。
- 用户仍能输入任意其他海外电商平台名称。
- 后端 API 和 JSONL 存储结构不变。
- 现有筛选、导出和概览继续按平台字符串工作。
- 全量测试通过。

## 后续可扩展

- 增加平台别名标准化。
- 增加平台维度概览统计。
- 增加平台专属解析模板。
- 增加团队可配置平台列表。
