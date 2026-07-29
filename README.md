# 客户使用问题归因智能体

本项目是海外电商客服会话分析工作台。首版支持人工粘贴或上传客服会话，对单条会话输出中文分析结论，帮助运营和分析专员判断客户使用产品时遇到的问题、可能业务原因、优先责任方和下一步动作。

## 本地运行

```powershell
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e ".[dev]"
python -m uvicorn customer_issue_agent.app:create_app --factory --reload
```

打开 `http://127.0.0.1:8000`。

## 安全约束

首版不批量请求模型供应商，不进行压力测试，不自动循环重试。默认使用本地规则归因，后续接入模型时保持单会话、低并发、可人工复核。
