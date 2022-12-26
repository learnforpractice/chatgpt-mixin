import os
import sys
import time
import asyncio
import base64
import logging
import httpx
import yaml
import traceback
import websockets
import platform
from typing import Optional, List, Dict, Any, Union, Set

from pymixin.mixin_ws_api import MixinWSApi, MessageView
from pymixin import utils
from pymixin import log

from dataclasses import dataclass
from playwright.async_api import async_playwright

from .chatgpt import ChatGPTBot

logger = log.get_logger(__name__)
logger.addHandler(log.handler)

@dataclass
class AnswerRequestTask:
    conversation_id: str
    user_id: str
    task: asyncio.Task

@dataclass
class SavedQuestion:
    conversation_id: str
    user_id: str
    data: str

class MixinBot(MixinWSApi):
    def __init__(self, config_file):
        f = open(config_file)
        config = yaml.safe_load(f)
        super().__init__(config['bot_config'], on_message=self.on_message)
        self.chatgpt_accounts = config['accounts']

        self.client_id = config['bot_config']['client_id']

        self.chat_gpt_client = httpx.AsyncClient(proxies={})
        self.tasks: List[SavedQuestion] = []
        self.saved_questions: Dict[str, SavedQuestion] = {}

        asyncio.create_task(self.handle_questions())

        self.developer_conversation_id = None
        self.developer_user_id = None

        if 'developer_conversation_id' in config:
            self.developer_conversation_id = config['developer_conversation_id']
            self.developer_user_id = config['developer_user_id']

        self.bots: List[ChatGPTBot] = []
        self.standby_bots: List[ChatGPTBot] = []
        self._paused = False

    @property
    def paused(self):
        return self._paused
    
    @paused.setter
    def paused(self, value):
        self._paused = value

    async def init(self):
        PLAY = await async_playwright().start()
        for account in self.chatgpt_accounts:
            user = account['user']
            psw = account['psw']
            bot = ChatGPTBot(PLAY, user, psw)
            await bot.init()
            self.bots.append(bot)

    def choose_bot(self, user_id):
        bots = []
        for bot in self.bots:
            if bot.standby:
                continue
            bots.append(bot)

        for bot in bots:
            try:
                user = bot.users[user_id]
                return bot
            except KeyError:
                pass

        bot_index = 0
        user_counts = [len(bot.users) for bot in bots]
        try:
            bot_index = user_counts.index(min(user_counts))
            return bots[bot_index]
        except ValueError:
            return None

    async def send_message_to_chat_gpt(self, conversation_id: str, user_id: str, message: str):
        bot = self.choose_bot(user_id)
        if not bot:
            logger.info('no available bot')
            self.save_question(conversation_id, user_id, message)
            #queue message
            return False
        try:
            count = 0
            async for msg in bot.send_message(user_id, message):
                await self.sendUserText(conversation_id, user_id, msg)
                count += 1
            await asyncio.sleep(1.0)
            if count > 1:
                pass
            await self.sendUserText(conversation_id, user_id, "[END]")
            return True
        except Exception as e:
            logger.exception(e)
        self.save_question(conversation_id, user_id, message)
        return False

    async def send_message_to_chat_gpt2(self, conversation_id, user_id, message):
        bot = self.choose_bot(user_id)
        if not bot:
            logger.info('no available bot')
            self.save_question(conversation_id, user_id, message)
            #TODO: queue message
            return False
        msgs: List[str] = []
        try:
            async for msg in bot.send_message(user_id, message):
                msgs.append(msg)
            await self.sendUserText(conversation_id, user_id, ''.join(msgs) + '\n[END]')
            return True
        except Exception as e:
            logger.exception(e)
        self.save_question(conversation_id, user_id, message)
        return False

    async def handle_questions(self):
        while True:
            await asyncio.sleep(15.0)
            handled_question = []
            saved_questions = self.saved_questions.copy()
            for user_id, question in saved_questions.items():
                try:
                    logger.info("++++++++handle question: %s", question.data)
                    if await self.send_message_to_chat_gpt2(question.conversation_id, question.user_id, question.data):
                        handled_question.append(user_id)
                except Exception as e:
                    logger.info("%s", str(e))
                    continue
            for question in handled_question:
                del self.saved_questions[question]

    def save_question(self, conversation_id, user_id, data):
        self.saved_questions[user_id] = SavedQuestion(conversation_id, user_id, data)

    async def handle_message(self, conversation_id, user_id, data):
        try:
            await self.send_message_to_chat_gpt(conversation_id, user_id, data)
        except Exception as e:
            logger.exception(e)
            if self.developer_user_id:
                await self.sendUserText(self.developer_conversation_id, self.developer_user_id, f"exception occur at:{time.time()}: {traceback.format_exc()}")

    async def handle_group_message(self, conversation_id, user_id, data):
        await self.send_message_to_chat_gpt2(conversation_id, user_id, data)

    async def on_message(self, id: str, action: str, msg: Optional[MessageView]):
        if action not in ["ACKNOWLEDGE_MESSAGE_RECEIPT", "CREATE_MESSAGE", "LIST_PENDING_MESSAGES"]:
            logger.info("unknow action %s", action)
            return

        if action == "ACKNOWLEDGE_MESSAGE_RECEIPT":
            return

        if not action == "CREATE_MESSAGE":
            return

        if not msg:
            return

        logger.info('++++++++conversation_id:%s', msg.conversation_id)

        await self.echoMessage(msg.message_id)

        logger.info('user_id %s', msg.user_id)
        logger.info("created_at %s",msg.created_at)

        if not msg.category in ["SYSTEM_ACCOUNT_SNAPSHOT", "PLAIN_TEXT", "SYSTEM_CONVERSATION", "PLAIN_STICKER", "PLAIN_IMAGE", "PLAIN_CONTACT"]:
            logger.info("unknown category: %s", msg.category)
            return

        if not msg.category == "PLAIN_TEXT" and msg.type == "message":
            return

        data = msg.data
        logger.info(data)
        data = base64.urlsafe_b64decode(data)

        if data.startswith(b'@'):
            index = data.find(b' ')
            if index == -1:
                return
            data = data[index + 1:]
        data = data.decode()
        logger.info(data)

        if data == 'hi':
            await self.sendUserText(msg.conversation_id, msg.user_id, "Hello, this is an intelligent question and answer robot. Is there anything I can help you with?")
            return
        elif data == '你好':
            await self.sendUserText(msg.conversation_id, msg.user_id, "你好，这是一个智能问答机器人，请问有什么可以帮到你的吗？")
            return
        elif data == 'こんにちは':
            await self.sendUserText(msg.conversation_id, msg.user_id, "こんにちは、こちらはインテリジェントな質問応答ロボットです。何かお手伝いできることはありますか？")
            return

        if utils.unique_conversation_id(msg.user_id, self.client_id) == msg.conversation_id:
            asyncio.create_task(self.handle_message(msg.conversation_id, msg.user_id, data))
        else:
            asyncio.create_task(self.handle_group_message(msg.conversation_id, msg.user_id, data))

    async def run(self):
        try:
            while not self.paused:
                try:
                    await super().run()
                except websockets.exceptions.ConnectionClosedError as e:
                    logger.exception(e)
                    self.ws = None
        except asyncio.CancelledError:
            if self.ws:
                await self.ws.close()
            logger.info("mixin websocket was cancelled!")

    async def close(self):
        for bot in self.bots:
            await bot.close()

bot: Optional[MixinBot]  = None

def exception_handler(loop, context):
    # loop.default_exception_handler(context)
    logger.info("exception_handler: %s", context)
    loop.close()

async def start(config_file):
    global bot
    bot = MixinBot(config_file)
    await bot.init()
    asyncio.create_task(bot.run())
    while not bot.paused:
        await asyncio.sleep(1.0)

async def stop():
    global bot
    await bot.ws.close()

async def resume():
    global bot
    bot.paused = False
    while not bot.paused:
        await asyncio.sleep(1.0)

def run():
    logger.info('++++++pid: %s', os.getpid())
    if len(sys.argv) < 2:
        if platform.system() == 'Windows':
            print("usage: python -m chatgpt_mixin config_file")
        else:
            print("usage: python3 -m chatgpt_mixin config_file")
        return
    asyncio.run(start(sys.argv[1]))

if __name__ == '__main__':
    run()
