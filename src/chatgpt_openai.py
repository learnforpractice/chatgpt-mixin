import os
import time
import json
import uuid
import asyncio
from typing import List, Dict, Tuple, Optional
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
    def __init__(self, api_key: str, model_id: str = 'text-davinci-003'):
        openai.api_key = api_key
        # model_id = 'text-davinci-003'
        self.model_id = model_id
        # self.conversations: Dict[str, Dict[str, Message]] = {}

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

    def generate_prompt(self, conversation_id: str, message: str) -> str:
        parent_message_id = self.get_last_message_id(conversation_id)

        current_time = datetime.now()
        formatted_time = current_time.strftime("%Y-%m-%d")

        assistant_label = "ChatGPT"
        # stop = "<|im_end|>\n\n"
        stop = "\n\n"
        prompt_induct = f"You are {assistant_label}, a large language model trained by OpenAI. You answer as concisely as possible for each response (e.g. don’t be verbose). It is very important that you answer as concisely as possible, so please remember this. If you are generating a list, do not have too many items. Keep the number of items short. Remember, provide a response to the user's question using the same language present in their message\n"
        prompt_induct += f"Current date: {formatted_time}\n\n"

        old_conversations: List[str] = []
        parent_messages: list[Message] = []
        total_length = len(prompt_induct)
        if parent_message_id:
            for _ in range(10):
                parent_message = self.get_parent_messsage(conversation_id, parent_message_id)
                assert parent_message
                parent_messages.append(parent_message)
                if not parent_message.parent_message_id:
                    break
                parent_message_id = parent_message.parent_message_id

            for parent_message in parent_messages:
                conversation = f"User:\n\n{parent_message.message}{stop}"
                conversation += f"{assistant_label}:\n\n{parent_message.completion}{stop}"
                total_length += len(conversation)
                if total_length > 2048:
                    break
                old_conversations.insert(0, conversation)
        return prompt_induct + \
            ''.join(old_conversations) + \
            f"User:\n\n{message}{stop}" + \
            f"{assistant_label}:\n"

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

        start_time = time.time()
        try:
            response = await openai.Completion.acreate(
                user=conversation_id,
                model=self.model_id,
                prompt=prompt,
                max_tokens=1024,
                temperature=0.7,
                presence_penalty=0.6,
                stream=True
            )
        except openai.error.InvalidRequestError as e:
            logger.exception(e)
            yield 'Sorry, I am not available now.'
            return
        yield '[BEGIN]'
        collected_events = []
        completion_text = ''
        tokens: List[str] = []

        async for event in response:
            collected_events.append(event)  # save the event response
            event_text = event['choices'][0]['text']  # extract the text
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
            if len(completion_text) > 1024:
                break
        reply = completion_text
        logger.info('++++response: %s', reply)
        self.add_messsage(conversation_id, message, reply)
        yield ''.join(tokens)
        return
