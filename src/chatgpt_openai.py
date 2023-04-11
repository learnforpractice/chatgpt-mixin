import asyncio
import json
import os
import shelve
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import openai
import tiktoken
from pymixin import log

logger = log.get_logger(__name__)
logger.addHandler(log.handler)

if not os.path.exists('.db'):
    os.mkdir('.db')
g_conversations = shelve.open(f".db/conversations")

default_role = 'You are a helpful assistant'
max_prompt_token = 3000
gpt_encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")

rate_limit_size = 5
rate_limit_window_seconds = 60

class RateLimitExceededError(Exception):
    pass

@dataclass
class Message:
    message: str
    parent_message_id: Optional[str]
    completion: str

class ChatGPTBot:
    def __init__(self, api_key: str, stream=True):
        openai.api_key = api_key
        self.conversation_id = uuid.uuid4()

        self.standby = False
        self.users: Dict[str, bool] = {}

        self.lock = asyncio.Lock()
        self.stream = stream
        self.rate_limits: Dict[str, deque] = {}

    async def init(self):
        pass

    async def close(self):
        global g_conversations
        if not g_conversations:
            return
        g_conversations.close()
        g_conversations = None

    def generate_key(self, conversation_id: str, message_id: str):
        return f'{conversation_id}-{message_id}'

    def get_parent_messsage(self, conversation_id: str, message_id: str) -> Optional[Message]:
        key = self.generate_key(conversation_id, message_id)
        if key in g_conversations:
            return g_conversations[key]
        return None

    def count_tokens(self, message) -> int:
        tokens = gpt_encoding.encode(message)
        return len(tokens)

    def add_messsage(self, conversation_id: str, query: str, reply: str) -> str:

        message_id = str(uuid.uuid4())
        key = self.generate_key(conversation_id, message_id)
        assert not key in g_conversations

        parent_message_id = self.get_last_message_id(conversation_id)
        message = Message(query, parent_message_id, reply)
        g_conversations[key] = message
        self.set_last_message_id(conversation_id, message_id)
        return message_id

    def get_last_message_id(self, conversation_id: str) -> Optional[str]:
        key = f'{conversation_id}-last_message_id'
        try:
            return g_conversations[key]
        except KeyError:
            return None

    def set_last_message_id(self, conversation_id: str, message_id):
        key = f'{conversation_id}-last_message_id'
        g_conversations[key] = message_id

    def clear_last_message_id(self, conversation_id: str):
        key = f'{conversation_id}-last_message_id'
        try:
            del g_conversations[key]
        except KeyError:
            pass

    def get_role(self, conversation_id: str) -> str:
        key = self.generate_key(conversation_id, 'role')
        try:
            return g_conversations[key]
        except KeyError:
            return default_role

    def set_role(self, conversation_id: str, role: str):
        if role == self.get_role(conversation_id):
            return
        key = self.generate_key(conversation_id, 'role')
        g_conversations[key] = role
        self.clear_last_message_id(conversation_id)

    def set_default_role(self, conversation_id: str):
        if default_role == self.get_role(conversation_id):
            return
        key = self.generate_key(conversation_id, 'role')
        g_conversations[key] = default_role
        self.clear_last_message_id(conversation_id)

    def generate_prompt(self, conversation_id: str, message: str) -> Optional[List[Dict[str, str]]]:
        parent_message_id = self.get_last_message_id(conversation_id)
        parent_messages: list[Message] = []
        total_length = 0
        content = self.get_role(conversation_id)
        tokens_count = self.count_tokens(content)

        context_messages=[]
        if not parent_message_id:
            context_messages.append({"role": "user", "content": message})
            return context_messages

        tokens_count += self.count_tokens(message)

        if tokens_count > max_prompt_token:
            return None

        #add latest conversations to prompt
        while True:
            parent_message = self.get_parent_messsage(conversation_id, parent_message_id)
            assert parent_message
            contents = ' '.join((parent_message.message, parent_message.completion))
            current_tokens_count = self.count_tokens(contents)
            # count unicode characters tokens
            if tokens_count + current_tokens_count > max_prompt_token:
                break
            tokens_count += current_tokens_count

            parent_messages.append(parent_message)
            parent_message_id = parent_message.parent_message_id
            if not parent_message_id:
                break
        logger.info("+++++++estimate the token count: %s", tokens_count)
        parent_messages.reverse()
        for parent_message in parent_messages:
            context_messages.append({"role": "user", "content": parent_message.message})
            context_messages.append({"role": "assistant", "content": parent_message.completion})

        context_messages.append({"role": "system", "content": content})
        context_messages.append({"role": "user", "content": message})
        return context_messages

    def check_rate_limit(self, conversation_id: str):
        try:
            request_timestamps = self.rate_limits[conversation_id]
        except KeyError:
            request_timestamps = deque(maxlen=rate_limit_size)
            self.rate_limits[conversation_id] = request_timestamps

        current_time = time.time()
        # Remove timestamps older than the window
        while request_timestamps and current_time - request_timestamps[0] > rate_limit_window_seconds:
            request_timestamps.popleft()

        # Check if the request limit has been reached
        if len(request_timestamps) >= rate_limit_size:
            raise RateLimitExceededError(f"Rate limit exceeded. You can make the next request after {request_timestamps[0] + rate_limit_window_seconds - current_time:.2f} seconds.")

        request_timestamps.append(current_time)

    async def send_message(self, conversation_id: str, message: str):
        try:
            self.check_rate_limit(conversation_id)
        except RateLimitExceededError as e:
            yield "[BEGIN]"
            yield str(e)
            return

        if message.startswith('/role '):
            role = message.split(' ', 1)[1]
            self.set_role(conversation_id, role)
            yield "[BEGIN]"
            yield "Done!"
            return
        elif message == '/role':
            role = self.get_role(conversation_id)
            yield "[BEGIN]"
            yield role
            return
        elif message == '/reset_role':
            role = self.set_default_role(conversation_id)
            yield "[BEGIN]"
            yield 'Done!'
            return
        elif message == '/reset':
            role = self.clear_last_message_id(conversation_id)
            yield "[BEGIN]"
            yield 'Done!'
            return

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
        # logger.info('+++prompt:%s', prompt)
        if not prompt:
            yield '[BEGIN]'
            yield 'oops, something went wrong, please try to reduce your worlds.'
            return
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
        if not prompt:
            yield '[BEGIN]'
            yield 'oops, something went wrong, please try to reduce your worlds.'
            return
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
