# 客户使用问题归因智能体

本项目是海外电商客服会话分析工作台。首版支持人工粘贴或上传客服会话，对单条会话输出中文分析结论，帮助运营和分析专员判断客户使用产品时遇到的问题、可能业务原因、优先责任方和下一步动作。

## 本地运行

```powershell
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e ".[dev]"
python -m uvicorn customer_issue_agent.app:create_app --factory --reload
```

打开 `http://127.0.0.1:8000`。

## 工作台使用方式

打开首页后可以选择两种输入方式：

- `粘贴会话`：选择平台来源，粘贴单条客服会话，然后点击“分析会话”。
- `上传文件`：选择平台来源，上传 `txt`、`log`、`csv`、`xlsx` 或 `xlsm` 文件，然后点击“上传并分析”。

分析完成后，页面会直接显示客户问题、业务原因、优先责任方、下一步建议和需要补充的信息。最近记录会保留最近 10 条分析摘要。

## 安全约束

首版不批量请求模型供应商，不进行压力测试，不自动循环重试。默认使用本地规则归因，后续接入模型时保持单会话、低并发、可人工复核。

## 手动验收样例

平台来源填写 `Other overseas platform`，客服会话填写：

```text
Customer: I followed the instructions but it still will not connect.
Agent: Please try again later.
```

预期结果包含：

- 客户问题：连接、配对或设置失败。
- 业务原因：说明或引导不清，且客服排障引导不足。
- 优先责任方：客服培训。
- 下一步建议：补问设备型号、系统版本、连接方式和错误提示。
