"""Serializable source/page diagnostics shared by preview, CLI and batch jobs."""
from dataclasses import asdict, dataclass


@dataclass
class Issue:
    severity: str
    source: str
    line: int
    section: str
    object: str
    reason: str
    page: int

    def to_dict(self):
        return asdict(self)

    def __str__(self):
        return f'[{self.severity}] {self.source}:{self.line} · {self.section} · {self.object} · 第 {self.page} 页：{self.reason}'


class ConversionNotice(UserWarning):
    def __init__(self, issue):
        self.issue = issue
        super().__init__(str(issue))

    def __str__(self):
        return str(self.issue)


def issue_data(notes):
    return [note.message.issue.to_dict() for note in notes
            if isinstance(note.message, ConversionNotice)]
