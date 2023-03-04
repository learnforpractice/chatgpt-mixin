import os
import time
import json
import uuid
import asyncio
from typing import List, Dict, Tuple, Optional, Any
import shelve
from datetime import datetime
from dataclasses import dataclass
import openai
from pymixin import log

logger = log.get_logger(__name__)
logger.addHandler(log.handler)

@dataclass
class Message:
    message: str
    parent_message_id: Optional[str]
    completion: str

if not os.path.exists('.db'):
    os.mkdir('.db')
g_conversations = shelve.open(f".db/conversations")

class ChatGPTBot:
    def __init__(self, api_key: str, stream=True):
        openai.api_key = api_key
        self.conversation_id = uuid.uuid4()

        self.standby = False
        self.users: Dict[str, bool] = {}

        self.lock = asyncio.Lock()
        self.stream = stream

    async def init(self):
        pass
    
    def generate_key(self, conversation_id: str, message_id: str):
        return f'{conversation_id}-{message_id}'

    def get_parent_messsage(self, conversation_id: str, message_id: str) -> Optional[Message]:
        key = self.generate_key(conversation_id, message_id)
        if key in g_conversations:
            return g_conversations[key]
        return None

    def add_messsage(self, conversation_id: str, query: str, reply: str) -> str:

        message_id = str(uuid.uuid4())
        key = self.generate_key(conversation_id, message_id)
        assert not key in g_conversations

        parent_message_id = self.get_last_message_id(conversation_id)
        message = Message(query, parent_message_id, reply)
        g_conversations[key] = message
        self.save_last_message_id(conversation_id, message_id)
        return message_id

    def get_last_message_id(self, conversation_id: str) -> Optional[str]:
        key = f'{conversation_id}-last_message_id'
        if key in g_conversations:
            return g_conversations[key]
        return None

    def save_last_message_id(self, conversation_id: str, message_id):
        key = f'{conversation_id}-last_message_id'
        g_conversations[key] = message_id

    def generate_prompt(self, conversation_id: str, message: str) -> List[Dict[str, str]]:
        parent_message_id = self.get_last_message_id(conversation_id)
        parent_messages: list[Message] = []
        total_length = 0
        context_messages=[
            {"role": "system", "content": "You are a helpful assistant"},
        ]
        if not parent_message_id:
            context_messages.append({"role": "user", "content": message})
            return context_messages

        #add latest 10 conversations to prompt
        for _ in range(10):
            parent_message = self.get_parent_messsage(conversation_id, parent_message_id)
            assert parent_message
            total_length += len(parent_message.message) + len(parent_message.completion)
            if total_length > 2048:
                break
            parent_messages.append(parent_message)
            parent_message_id = parent_message.parent_message_id
            if not parent_message_id:
                break

        parent_messages.reverse()
        for parent_message in parent_messages:
            context_messages.append({"role": "user", "content": parent_message.message})
            context_messages.append({"role": "assistant", "content": parent_message.completion})

        context_messages.append({"role": "user", "content": message})
        return context_messages

    async def send_message(self, conversation_id: str, message: str):
        async with self.lock:
            if self.stream:
                async for msg in self._send_message_stream(conversation_id, message):
                    yield msg
            else:
                async for msg in self._send_message(conversation_id, message):
                    yield msg

    async def _send_message(self, conversation_id: str, message: str):
        if len(message) == 0:
            return
        self.users[conversation_id] = True

        prompt = self.generate_prompt(conversation_id, message)
        logger.info('+++prompt:%s', prompt)
        try:
            yield '[BEGIN]'
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=prompt
            )
        except openai.error.InvalidRequestError as e:
            logger.exception(e)
            yield 'Sorry, I am not available now.'
            return
        reply = response['choices'][0]['message']['content']
        logger.info('++++response: %s', reply)
        self.add_messsage(conversation_id, message, reply)
        yield reply
        return

    async def _send_message_stream(self, conversation_id: str, message: str):
        if len(message) == 0:
            return
        self.users[conversation_id] = True

        prompt = self.generate_prompt(conversation_id, message)
        start_time = time.time()
        try:
            yield '[BEGIN]'
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=prompt,
                stream=True
            )
        except openai.error.InvalidRequestError as e:
            logger.exception(e)
            yield 'Sorry, I am not available now.'
            return
        collected_events = []
        completion_text = ''
        tokens: List[str] = []

        async for event in response:
            collected_events.append(event)  # save the event response
            # logger.info(event)
            delta = event['choices'][0]['delta']
            if not delta:
                break
            if not 'content' in delta:
                continue
            event_text = delta['content']  # extract the text
            tokens.append(event_text)
            if event_text.endswith('\n'):
                if time.time() - start_time > 3.0:
                    start_time = time.time()
                    reply = ''.join(tokens)
                    reply = reply.strip()
                    if reply:
                        yield reply
                    tokens = []
            completion_text += event_text  # append the text
        reply = completion_text
        logger.info('++++response: %s', reply)
        self.add_messsage(conversation_id, message, reply)
        yield ''.join(tokens)
        return
