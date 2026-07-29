from dev_agent.runtime.models import RuntimeContext


def build_task_prompt(context: RuntimeContext) -> str:
    memory_lines = [f"- [{hit.kind}:{hit.record_id}] {hit.text}" for hit in context.memory_hits] or [
        "- 无相关历史经验"
    ]
    verification_lines = [
        f"- {step.name}: {' '.join(step.command)}" for step in context.verification_plan.steps
    ] or ["- 无可推断验证命令"]
    return "\n".join(
        [
            f"用户请求：{context.user_request}",
            f"项目：{context.project.name}",
            f"技术栈：{', '.join(context.project.tech_stack or context.scan.languages)}",
            f"语言偏好：{context.preferences.language}",
            "项目规则：",
            context.rules_text or "无项目规则",
            "扫描结果：",
            f"- languages: {', '.join(context.scan.languages)}",
            f"- markers: {', '.join(context.scan.markers)}",
            "Git 状态：",
            context.git.status or "工作区干净",
            "近期 Git 记录：",
            context.git.recent_log or "无 Git 记录",
            "相关历史：",
            *memory_lines,
            "建议验证：",
            *verification_lines,
            "请给出简洁、可执行、以验证为中心的研发计划。",
        ]
    )
