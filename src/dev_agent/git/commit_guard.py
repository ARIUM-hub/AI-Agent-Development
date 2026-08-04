from dev_agent.git.models import GitCommitPreflightError, GitStatusEntry


def validate_commit_message(message: str) -> str:
    if not message.strip():
        raise GitCommitPreflightError("--commit-message 不能为空")
    if len(message) > 200:
        raise GitCommitPreflightError("--commit-message 不能超过 200 个字符")
    if any(char in message for char in ("\r", "\n", "\0")):
        raise GitCommitPreflightError("--commit-message 必须是单行文本")
    return message


def parse_porcelain_v1_z(raw: str) -> tuple[GitStatusEntry, ...]:
    records = raw.split("\0")
    if records and records[-1] == "":
        records.pop()
    entries: list[GitStatusEntry] = []
    index = 0
    while index < len(records):
        record = records[index]
        if len(record) < 4 or record[2] != " ":
            raise GitCommitPreflightError("无法解析 Git 状态")
        x, y, path = record[0], record[1], record[3:]
        original_path = None
        if x in {"R", "C"} or y in {"R", "C"}:
            index += 1
            if index >= len(records):
                raise GitCommitPreflightError("无法解析 Git 状态中的重命名记录")
            original_path = records[index]
        entries.append(GitStatusEntry(x, y, path, original_path))
        index += 1
    return tuple(entries)
