"""消息组件（AstrBot 风格的 Plain/At/Image/Record/Face）。"""


class BaseMessageComponent:
    pass


class Plain(BaseMessageComponent):
    def __init__(self, text: str = ""):
        self.text = text

    def __repr__(self):
        return f"Plain({self.text!r})"


class At(BaseMessageComponent):
    def __init__(self, qq: str = ""):
        self.qq = str(qq)


class Image(BaseMessageComponent):
    def __init__(self, file=None, url=None):
        self.file = file
        self.url = url


class Record(BaseMessageComponent):
    def __init__(self, file=None):
        self.file = file


class Face(BaseMessageComponent):
    def __init__(self, id=None):
        self.id = id
