"""INI 语法高亮（节名 / 键 / 值 / 注释）。"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


class IniHighlighter(QSyntaxHighlighter):
    def __init__(self, document, dark: bool = True):
        super().__init__(document)
        self._dark = dark
        self._rebuild_formats()

    def _rebuild_formats(self):
        if self._dark:
            self.fmt_comment = self._fmt("#6a9955")
            self.fmt_section = self._fmt("#dcdcaa", bold=True)
            self.fmt_key = self._fmt("#9cdcfe")
            self.fmt_equals = self._fmt("#d4d4d4")
            self.fmt_value = self._fmt("#ce9178")
            self.fmt_plus = self._fmt("#c586c0")
        else:
            self.fmt_comment = self._fmt("#008000")
            self.fmt_section = self._fmt("#0000ff", bold=True)
            self.fmt_key = self._fmt("#001080")
            self.fmt_equals = self._fmt("#000000")
            self.fmt_value = self._fmt("#a31515")
            self.fmt_plus = self._fmt("#af00db")

    @staticmethod
    def _fmt(color: str, bold: bool = False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:
            f.setFontWeight(QFont.Bold)
        return f

    def highlightBlock(self, text: str):
        s = text
        stripped = s.lstrip()
        if not stripped:
            return
        # 整行注释
        if stripped.startswith(";"):
            self.setFormat(0, len(s), self.fmt_comment)
            return
        # [Section]
        if stripped.startswith("["):
            idx = s.find("[")
            end = s.find("]", idx)
            if end >= 0:
                self.setFormat(idx, end - idx + 1, self.fmt_section)
                # 节名行尾注释
                rest = s[end + 1 :]
                c = rest.find(";")
                if c >= 0:
                    self.setFormat(end + 1 + c, len(s) - (end + 1 + c), self.fmt_comment)
            else:
                self.setFormat(0, len(s), self.fmt_section)
            return
        # += value
        st = stripped
        lead = len(s) - len(stripped)
        if st.startswith("+="):
            self.setFormat(lead, 2, self.fmt_plus)
            val_start = lead + 2
            c = s.find(";", val_start)
            if c >= 0:
                self.setFormat(val_start, c - val_start, self.fmt_value)
                self.setFormat(c, len(s) - c, self.fmt_comment)
            else:
                self.setFormat(val_start, len(s) - val_start, self.fmt_value)
            return
        # key=value
        eq = s.find("=")
        if eq < 0:
            return
        # 键（等号前）
        self.setFormat(0, eq, self.fmt_key)
        self.setFormat(eq, 1, self.fmt_equals)
        # 值与行尾注释
        c = s.find(";", eq + 1)
        if c >= 0:
            self.setFormat(eq + 1, c - eq - 1, self.fmt_value)
            self.setFormat(c, len(s) - c, self.fmt_comment)
        else:
            self.setFormat(eq + 1, len(s) - eq - 1, self.fmt_value)
