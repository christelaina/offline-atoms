from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class Note:
    path: Path
    title: str
    content: str = ""
    headings: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    wikilinks: List[str] = field(default_factory=list)
    frontmatter: dict[str, str] = field(default_factory=dict)

    @property
    def relative_path(self) -> str:
        return self.path.as_posix()

    @property
    def slug(self) -> str:
        return self.path.stem
