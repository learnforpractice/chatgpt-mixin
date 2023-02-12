# -*- coding: utf-8 -*-

import os
import sys
import time
import asyncio
import base64
import yaml
import traceback
import websockets
import platform
import httpx
from datetime import datetime
from typing import Optional, List, Dict, Any, Union, Set

from pymixin.mixin_ws_api import MixinWSApi, MessageView
from pymixin import utils
from pymixin import log

from dataclasses import dataclass

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

sayhi = {
    'hi': '''
Hello, this is an intelligent question and answer robot. Is there anything I can help you with?

here is a list of things that I As an AI language model, can do, along with a brief explanation of each:

- Answer questions: I can provide information and assistance on a wide range of topics, such as science, history, technology, and general knowledge.

- Generate text: I can create original text on a variety of topics, including stories, news articles, and descriptions.

- Translate text: I can translate text from one language to another using machine translation technology.

- Summarize text: I can provide a concise overview of the main points of a long piece of text.

- Provide definitions: I can provide definitions and explanations of words, phrases, and concepts.

- Generate responses: I can generate appropriate and coherent responses to prompts, such as questions or statements.

- Process and analyze data: I can process and analyze large amounts of data in order to extract useful insights and information.

- Identify patterns and trends in data: I can identify patterns and trends in data sets, which can be useful for a variety of applications, such as predicting future outcomes or identifying relationships between variables.

- Recognize and classify images: I can recognize and classify objects and features in images using machine learning algorithms.

- Provide recommendations: I can make recommendations based on data and analysis, such as suggesting products or courses of action.

- Perform tasks based on instructions: I can perform tasks or actions based on specific instructions, such as creating a list or completing a calculation.
    ''',

    '你好': '''
你好，这是一个智能问答机器人，请问有什么可以帮到你的吗？

以下是我可以做的事情：

- 回答问题：我可以提供有关科学、历史、技术和常识等广泛主题的信息和帮助。

- 生成文本：我可以创建有关各种主题的原创文本，包括故事、新闻文章和描述。

- 翻译文本：我可以使用机器翻译技术将文本从一种语言翻译成另一种语言。

- 摘要文本：我可以为长篇文章的主要要点提供简明概述。

- 提供定义：我可以为单词、短语和概念提供定义和解释。

- 生成响应：我可以以连贯和适当的方式生成对询问或陈述等提示的响应。

- 处理和分析数据：我可以处理和分析大量数据，以提取有用的信息和见解。

- 识别数据中的模式和趋势：我可以识别数据集中的模式和趋势，这对于预测未来结果或识别变量之间关系等应用是有用的。

- 识别和分类图像：我可以使用机器学习算法识别和分类图像中的对象和特征。例如，我可以识别图像中的人、动物、植物等，并将它们分类到不同的类别中。

- 提供建议：我可以根据数据和分析提供建议，如建议产品或行动方案。

- 根据指令执行任务：我可以根据特定的指令执行任务或动作，例如创建清单或完成计算。
    ''',

    'こんにちは': '''
こんにちは、こちらはインテリジェントな質問応答ロボットです。何かお手伝いできることはありますか？

はい、これは私が人工知能言語モデルとしてできることのリストです。簡単な説明も付けます：

- 質問に答える：科学、歴史、技術、一般常識など、幅広いテーマについての情報やアシスタンスを提供できます。

- テキストを生成する：話、ニュース記事、説明など、様々なテーマについてのオリジナルテキストを作成できます。

- テキストを翻訳する：機械翻訳技術を使用して、1つの言語から別の言語へテキストを翻訳できます。

- テキストを要約する：長い文章の主要ポイントを簡潔に概要できます。

- 定義を提供する：単語、フレーズ、概念などの定義と解説を提供できます。

- レスポンスを生成する：質問や文章などのプロンプトに対する、コヒーレントで適切なレスポンスを生成できます。

- データを処理して分析する：大量のデータを処理して、有用な情報や見解を抽出できます。

- データ中のパターンやトレンドを特定する：データセット中のパターンやトレンドを特定できます。これは、将来のアウトカムを予測したり、変数間の関係を特定するような様々なアプリケーションに役立ちます。

- 画像を認識して分類する：機械学習アルゴリズムを使用して、画像中の物体や特徴を認識して、異なるカテゴリーに分類できます。例えば、画像中の人や動物、植物などを認識し、それらを異なるカテゴリーに分類できます。

- アドバイスを提供する：データや分析に基づいて、製品を提案するようなアドバイスを提供できます。

- 指令に基づいてタスクを実行する：清单を作成するような特定の指令に基づいて、タスクやアクションを実行できます。
    '''
}

class MixinBot(MixinWSApi):
    def __init__(self, config_file):
        f = open(config_file)
        config = yaml.safe_load(f)
        super().__init__(config['bot_config'], on_message=self.on_message)
        self.chatgpt_accounts = config['accounts']
        self.openai_api_keys = config['openai_api_keys']

        self.client_id = config['bot_config']['client_id']

        self.tasks: List[SavedQuestion] = []
        self.saved_questions: Dict[str, SavedQuestion] = {}

        self.developer_conversation_id = None
        self.developer_user_id = None
        self.web_client = httpx.AsyncClient()

        if 'developer_conversation_id' in config:
            self.developer_conversation_id = config['developer_conversation_id']
            self.developer_user_id = config['developer_user_id']
        # openai_api_key
        self.bots = []
        self.standby_bots = []
        self._paused = False

    @property
    def paused(self):
        return self._paused
    
    @paused.setter
    def paused(self, value):
        self._paused = value

    async def init(self):
        asyncio.create_task(self.handle_questions())

        if self.chatgpt_accounts:
            from playwright.async_api import async_playwright
            from .chatgpt_browser import ChatGPTBot
            PLAY = await async_playwright().start()
            for account in self.chatgpt_accounts:
                user = account['user']
                psw = account['psw']
                bot = ChatGPTBot(PLAY, user, psw)
                await bot.init()
                self.bots.append(bot)

        if self.openai_api_keys:
            from .chatgpt_openai import ChatGPTBot
            for key in self.openai_api_keys:
                bot = ChatGPTBot(key)
                await bot.init()
                self.bots.append(bot)
        
        assert self.bots

    def choose_bot(self, user_id):
        bots = []
        for bot in self.bots:
            if bot.standby:
                continue
            bots.append(bot)

        for bot in bots:
            if user_id in bot.users:
                return bot

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
        if message.startswith('/web'):
            message = message.replace('/web', '', 1)
            old_message = message
            message = await self.get_web_result(message)
            if not old_message == message:
                await self.sendUserText(conversation_id, user_id, message)
        try:
            async for msg in bot.send_message(user_id, message):
                await self.sendUserText(conversation_id, user_id, msg)
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

        if message.startswith('/web'):
            message = message.replace('/web', '', 1)
            old_message = message
            message = await self.get_web_result(message)
            if not old_message == message:
                await self.sendUserText(conversation_id, user_id, message)

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

    async def handle_message(self, conversation_id, user_id, message):
        try:
            await self.send_message_to_chat_gpt(conversation_id, user_id, message)
        except Exception as e:
            logger.exception(e)
            if self.developer_user_id:
                await self.sendUserText(self.developer_conversation_id, self.developer_user_id, f"exception occur at:{time.time()}: {traceback.format_exc()}")

    async def get_web_result(self, message: str):
        date = datetime.now()
        formatted_date = date.strftime('%m/%d/%Y')
        prompt = message
        search = message
        if message.count('/p ') == 1:
            search, prompt = message.split('/p ')
        logger.info("+++++%s %s", search, prompt)
        url = f'https://ddg-webapp-aagd.vercel.app/search?max_results=3&q="{search}"'
        r = httpx.get(url)
        results: List[Any] = r.json()
        logger.info("++++++results: %s", results)
        if not results:
            return prompt
        counter = 0
        querys = []
        querys.append("Web search results:\n\n")
        for a in results:
            counter += 1
            body = a['body']
            href = a['href']
            querys.append(f'[{counter}] "{body}"')
            querys.append(f"Source: {href}")
        querys.append(f"\nCurrent date: {formatted_date}")
        querys.append(f"\nInstructions: Using the provided web search results, write a comprehensive reply to the given prompt. Make sure to cite results using [[number](URL)] notation after the reference. If the provided search results refer to multiple subjects with the same name, write separate answers for each subject.\nPrompt: {prompt}")
        return "\n".join(querys)
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

        try:
            reply = sayhi[data]
            await self.sendUserText(msg.conversation_id, msg.user_id, reply)
            return
        except KeyError:
            pass

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
                #asyncio.exceptions.TimeoutError
                except Exception as e:
                    logger.exception(e)
                    self.ws = None
        except asyncio.CancelledError:
            if self.ws:
                await self.ws.close()
            if self.web_client:
                await self.web_client.aclose()
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
    print('started')
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
