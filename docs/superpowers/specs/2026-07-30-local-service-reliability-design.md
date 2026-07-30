# 本地服务可靠性加固设计

## 背景

当前项目已经具备以下本地常驻启动能力：

- 通过 `scripts/start-local-service.ps1` 统一启动 `customer_issue_agent`
- 通过 `scripts/register-local-service-task.ps1` 在用户登录时注册计划任务
- 启动时会校验 editable 安装路径、清理旧 `uvicorn` 进程，并固定监听 `http://localhost:58623`

这已经显著降低了“旧 worktree 漂移”与“旧进程残留”导致的不可访问问题，但仍存在两个现实风险：

1. 登录时如果恰好启动失败，当前任务不会自动补拉起
2. 用户后续遇到无法访问时，缺少一个面向人工恢复的单入口自检/自愈脚本

本次设计只聚焦于进一步降低“偶发无法访问”的概率，不引入高频健康检查、循环探测或多实例后台守护。

## 目标

- 给登录计划任务增加有限次数的失败自动重试能力
- 提供一个项目内的一键自检并自愈脚本
- 保持单实例、低频、可人工理解的恢复模型
- 保持现有固定地址 `http://localhost:58623`

## 非目标

- 不增加持续轮询式健康检查
- 不增加额外的定时巡检任务
- 不改为 Windows Service / NSSM / WinSW
- 不引入多端口、多副本或负载均衡

## 方案对比

### 方案 A：仅增加一键修复脚本

优点：

- 改动最小
- 行为最可控

缺点：

- 登录时的偶发失败仍然完全依赖人工干预

### 方案 B：登录任务失败自动重试 + 一键修复脚本（推荐）

优点：

- 登录瞬间失败可自动恢复，覆盖最常见的临时异常
- 用户仍保留一条明确的手动恢复入口
- 不需要持续探测，也不会形成高频请求风险

缺点：

- 计划任务配置会稍微复杂一些

### 方案 C：B + 额外定时巡检任务

优点：

- 自恢复能力最强

缺点：

- 复杂度上升
- 更容易逐步滑向后台持续探测
- 与当前“低频、安全、可解释”目标不完全一致

本次采用方案 B。

## 架构设计

### 1. 启动入口保持单一

`scripts/start-local-service.ps1` 仍然是唯一真正负责启动服务的脚本：

- 解析真实 Python 解释器
- 校验 editable 安装是否指向当前 worktree 的 `src`
- 必要时使用国内源执行 `pip install -e ".[dev]"`
- 清理旧 `customer_issue_agent` `uvicorn` 进程
- 固定启动到 `127.0.0.1:58623`

新能力不会绕过这个入口，所有自动恢复和手动恢复都最终调用它。

### 2. 计划任务增加有限失败重试

`scripts/register-local-service-task.ps1` 注册计划任务时，补充任务设置：

- `RestartCount = 3`
- `RestartInterval = 00:01:00`
- 保留 `MultipleInstances = IgnoreNew`
- 保留登录触发器 `AtLogOn`

含义是：如果登录启动这次失败，Windows 最多再尝试 3 次，每次间隔 1 分钟。

这样可以覆盖：

- 登录时磁盘/环境暂时未准备好
- 首次拉起时解释器或依赖短暂异常
- 上次异常退出后第一次拉起失败

同时它仍然是有限次数、非循环探测，不会造成高频请求。

### 3. 新增一键自检并自愈脚本

新增 `scripts/repair-local-service.ps1`，职责是：

- 检查计划任务 `CustomerIssueAgentLocalService` 是否存在
- 检查 editable 安装是否指向当前 worktree
- 检查 `58623` 端口是否被错误进程占用
- 检查 `http://localhost:58623/api/records/summary` 是否可达
- 如果任务缺失，则提示或自动重新注册
- 如果服务不健康，则调用 `start-local-service.ps1 -ForceRestart`

该脚本只执行一次，不做循环监控。

### 4. 人工恢复路径

后续推荐的人工恢复路径统一为：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\repair-local-service.ps1
```

如果用户只想单纯重启，也仍可直接调用：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-service.ps1 -ForceRestart
```

## 文件边界

### 修改

- `scripts/register-local-service-task.ps1`
  - 增加计划任务失败重试设置
  - dry-run 输出增加恢复配置字段

- `README.md`
  - 文档化新的恢复命令
  - 说明计划任务会做有限失败重试

### 新增

- `scripts/repair-local-service.ps1`
  - 自检并自愈入口

- `tests/test_service_scripts.py`
  - 覆盖恢复脚本 dry-run 输出
  - 覆盖计划任务重试配置 dry-run 输出

## 数据流

### 登录启动

1. Windows 登录触发 `CustomerIssueAgentLocalService`
2. 计划任务执行 `start-local-service.ps1`
3. 启动成功则保持运行
4. 启动失败则由任务设置自动重试，最多 3 次

### 手动修复

1. 用户执行 `repair-local-service.ps1`
2. 脚本检查任务、editable 路径、端口占用和健康接口
3. 如果发现异常，则调用 `start-local-service.ps1 -ForceRestart`
4. 输出本次检查与修复动作

## 错误处理

### 端口被其他非目标进程占用

行为：

- 不强行杀死无关进程
- 明确输出占用 PID
- 返回非零退出码，提示用户先释放端口

### Python 不可用

行为：

- 输出清晰错误
- 不继续执行部分修复动作

### 计划任务缺失

行为：

- `repair-local-service.ps1` 输出缺失状态
- 默认自动重新注册一次

### 服务已健康运行

行为：

- 不重复启动
- 输出 `service_already_running`

## 测试策略

### 自动化测试

基于 `tests/test_service_scripts.py` 增加两类断言：

1. `register-local-service-task.ps1 -DryRun`
   - 输出任务名
   - 输出登录触发器
   - 输出重试次数和重试间隔

2. `repair-local-service.ps1 -DryRun`
   - 输出项目根目录
   - 输出服务 URL
   - 输出会检查任务、健康状态和启动脚本调用意图

### 手动验证

1. 重新注册计划任务
2. 读取任务配置，确认有 `RestartCount=3`、`RestartInterval=00:01:00`
3. 执行 `repair-local-service.ps1`
4. 访问 `http://localhost:58623`

## 风险与缓解

### 风险：自动重试把错误重复 3 次

缓解：

- 次数有限
- 只在任务失败后触发
- 间隔固定为 1 分钟，避免瞬时重放

### 风险：修复脚本误杀无关进程

缓解：

- 只处理命令行匹配 `customer_issue_agent.app:create_app` 的 `uvicorn` 进程
- 非目标进程占用端口时只报错，不强杀

### 风险：恢复逻辑过度复杂

缓解：

- 保持单入口
- 不引入巡检任务
- 不做后台循环

## 验收标准

- 计划任务注册后具备有限失败重试配置
- `repair-local-service.ps1` 可以作为单独入口执行
- 自动测试覆盖新增 dry-run 输出
- 现有服务访问地址仍为 `http://localhost:58623`
- 全量测试保持通过
