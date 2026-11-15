"""示例 AstrBot 插件（最小 Hello World）—— 验证兼容层。"""
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


@register("helloworld", "FotlimBOT", "一个简单的 Hello World 插件", "1.0.0")
class HelloWorld(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """发送 /helloworld 触发，回复 Hello, {昵称}!"""
        yield event.plain_result("Hello, %s!" % event.get_sender_name())

    @filter.command("help")
    async def help(self, event: AstrMessageEvent):
        """发送 /help 触发"""
        yield event.plain_result("我是 FotlimBOT～指令：/helloworld /ping")
