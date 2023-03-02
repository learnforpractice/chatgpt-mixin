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

class ChatGPTBot:
    def __init__(self, api_key: str):
        openai.api_key = api_key
        self.conversation_id = uuid.uuid4()

        if not os.path.exists('.db'):
            os.mkdir('.db')
        self.conversations = shelve.open(f".db/conversations")

        self.standby = False
        self.users: Dict[str, bool] = {}

        self.lock = asyncio.Lock()

    async def init(self):
        pass
    
    def generate_key(self, conversation_id: str, message_id: str):
        return f'{conversation_id}-{message_id}'

    def get_parent_messsage(self, conversation_id: str, message_id: str) -> Optional[Message]:
        key = self.generate_key(conversation_id, message_id)
        if key in self.conversations:
            return self.conversations[key]
        return None

    def add_messsage(self, conversation_id: str, query: str, reply: str) -> str:

        message_id = str(uuid.uuid4())
        key = self.generate_key(conversation_id, message_id)
        assert not key in self.conversations

        parent_message_id = self.get_last_message_id(conversation_id)
        message = Message(query, parent_message_id, reply)
        self.conversations[key] = message
        self.save_last_message_id(conversation_id, message_id)
        return message_id

    def get_last_message_id(self, conversation_id: str) -> Optional[str]:
        key = f'{conversation_id}-last_message_id'
        if key in self.conversations:
            return self.conversations[key]
        return None

    def save_last_message_id(self, conversation_id: str, message_id):
        key = f'{conversation_id}-last_message_id'
        self.conversations[key] = message_id

    def generate_prompt(self, conversation_id: str, message: str) -> List[Dict[str, str]]:
        parent_message_id = self.get_last_message_id(conversation_id)
        # stop = "<|im_end|>\n\n"
        parent_messages: list[Message] = []
        total_length = 0
        context_messages=[
            {"role": "system", "content": "You are a helpful assistant."},
        ]
        if parent_message_id:
            for _ in range(10):
                parent_message = self.get_parent_messsage(conversation_id, parent_message_id)
                assert parent_message
                parent_messages.append(parent_message)
                if not parent_message.parent_message_id:
                    break
                parent_message_id = parent_message.parent_message_id

            parent_messages.reverse()
            for parent_message in parent_messages:
                context_messages.append({"role": "user", "content": parent_message.message})
                context_messages.append({"role": "assistant", "content": parent_message.completion})
                total_length += len(parent_message.message) + len(parent_message.completion)
                if total_length > 2048:
                    break
        context_messages.append({"role": "user", "content": message})
        return context_messages

    async def send_message(self, conversation_id: str, message: str):
        async with self.lock:
            async for msg in self._send_message(conversation_id, message):
                yield msg

    async def _send_message(self, conversation_id: str, message: str):
        if len(message) == 0:
            return
        self.users[conversation_id] = True

        prompt = self.generate_prompt(conversation_id, message)
        if len(prompt) > 3000:
            yield 'Error: query too large!'
            return
        logger.info('+++prompt:%s', prompt)
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=prompt
            )
        except openai.error.InvalidRequestError as e:
            logger.exception(e)
            yield 'Sorry, I am not available now.'
            return
        yield '[BEGIN]\n'
        reply = response['choices'][0]['message']['content']
        logger.info('++++response: %s', reply)
        self.add_messsage(conversation_id, message, reply)
        yield reply
        return
