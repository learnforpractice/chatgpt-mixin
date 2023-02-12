import os
import shutil
from dataclasses import dataclass
from typing import List

import pytest

import openai
from chatgpt_openai import ChatGPTBot

file_dir = os.path.dirname(os.path.realpath(__file__))

def test_save_message_id():
    bot = ChatGPTBot('test')
    bot.save_last_message_id('conversation_id', 'message_id')
    assert bot.get_last_message_id('conversation_id') == 'message_id'

@pytest.mark.asyncio
async def test_prompt():
    if os.path.exists(f'{file_dir}/.db'):
        # remove db
        shutil.rmtree(f'{file_dir}/.db')
    @classmethod
    async def acreate(cls, *args, **kwargs):
        @dataclass
        class Choice:
            text: str

        @dataclass
        class Completion:
            choices: List[Choice]
        completion = Completion([Choice('test')])
        return completion

    openai.Completion.acreate = acreate

    bot = ChatGPTBot('test')

    reply = await bot.send_message('conversation_id', 'hello')
    assert reply == 'test'
    message_id_1 = bot.get_last_message_id('conversation_id')

    reply = await bot.send_message('conversation_id', 'hello')
    assert reply == 'test'

    print(bot.get_last_message_id('conversation_id'))
    parent_message_id = bot.get_last_message_id('conversation_id')


    message = bot.get_parent_messsage('conversation_id', parent_message_id)
    assert message_id_1 == message.parent_message_id

    message = bot.get_parent_messsage('conversation_id', message.parent_message_id)
    print(message.parent_message_id)


@pytest.mark.asyncio
async def test_prompt_2():
    if os.path.exists(f'{file_dir}/.db'):
        # remove db
        shutil.rmtree(f'{file_dir}/.db')
    api_key = "sk-xxx"
    bot = ChatGPTBot(api_key)

    async for reply in bot.send_message('conversation_id', 'write a poem about a cat'):
        print('++++reply:', reply)

    async for reply in bot.send_message('conversation_id', 'make the poem rhyme'):
        print('+++reply:', reply)

    print(reply)
