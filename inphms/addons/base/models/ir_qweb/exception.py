from __future__ import annotations


class QWebError(Exception):
    def __init__(self, qweb: QWebErrorInfo):
        super().__init__('Error while rendering the template')
        self.qweb = qweb

    def __str__(self):
        return f'{super().__str__()}:\n    {self.qweb}'


class QWebErrorInfo:
    def __init__(self, error: str, ref_name: str | int | None, ref: int | None, path: str | None, element: str | None, source: list[tuple[int | str, str, str]]):
        self.error = error
        self.template = ref_name
        self.ref = ref
        self.path = path
        self.element = element
        self.source = source

    def __str__(self):
        info = [self.error]
        if self.template is not None:
            info.append(f'Template: {self.template}')
        if self.ref is not None:
            info.append(f'Reference: {self.ref}')
        if self.path is not None:
            info.append(f'Path: {self.path}')
        if self.element is not None:
            info.append(f'Element: {self.element}')
        if self.source:
            source = '\n          '.join(str(v) for v in self.source)
            info.append(f'From: {source}')
        return '\n    '.join(info)
