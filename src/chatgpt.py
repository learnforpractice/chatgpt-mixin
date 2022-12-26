import os
import json
import time
import uuid
import random
import asyncio
import logging
import shelve

from typing import Optional, Dict, Tuple, Any

# from playwright_stealth import stealth_sync, stealth_async
from cf_clearance2 import async_stealth


from pymixin import log
logger = log.get_logger(__name__)
logger.addHandler(log.handler)

class ChatGPTException(Exception):
    def __init__(self, error):
        super().__init__(self)
        self.error = error

    def __repr__(self):
        return self.error

    def __str__(self):
        return self.error

class TooManyRequestsException(ChatGPTException):
    pass

auto_send_messages = [
    "Hello",
    "Hi",
    "Hey",
    "How are you?",
    "What's up?",
    "Yo",
]

class MessageParser:
    def __init__(self):
        self.pos = 0
        self.message = None
        self.start = time.time()

    def feed(self, message: str):
        self.message = message

    def get_message(self):
        if time.time() - self.start < 1.0:
            return None
        try:
            last_index = self.message.rindex('\n\n', self.pos)
            pos = self.pos
            self.pos = last_index + 2
            self.start = time.time()
            return self.message[pos: self.pos]
        except ValueError:
            return None

    def get_remanent_message(self):
        return self.message[self.pos:]

class ChatGPTUser:

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.conversation_id = None
        self.parent_message_id = None
        self.expiration = time.time() + 15*60.0

    def reset_expiration(self):
        self.expiration = time.time() + 15*60.0

    def is_expired(self):
        return self.expiration < time.time()

class ChatGPTBot:

    def __init__(self, PLAY: Any, user: str, password: str):
        self.page: Optional[Any] = None
        self.access_token: Optional[str] = None

        self.PLAY = PLAY
        self.user = user
        self.password = password
        self._standby: bool = False
        self._busy: bool = False

        self.lock = asyncio.Lock()

        self.conversation_id = None
        self.parent_message_id = None

        if not os.path.exists('.db'):
            os.mkdir('.db')
        self.users = shelve.open(f".db/{user}-1")
        self.expired_user = shelve.open(f".db/{user}-2")

        self.alive_counter = 0

    @property
    def standby(self):
        return self._standby

    @standby.setter
    def standby(self, value):
        self._standby = value

    @property
    def busy(self):
        return self._busy

    @busy.setter
    def busy(self, value):
        self._busy = value

    def handle_expired_user(self, user: ChatGPTUser):
        try:
            self.expired_user[user.user_id] = user
            del self.users[user.user_id]
        except KeyError:
            pass

    def reset_alive_counter(self):
        self.alive_counter = 0

    async def heart_beat(self):
        try:
            while True:
                await self.check_expiration()
                await self.keep_alive()
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            logger.info("+++++++saving data on exit...")
            self.close()

    def close(self):
        self.users.close()
        self.expired_user.close()

    async def check_expiration(self):
        for user in self.users:
            if user.is_expired():
                self.handle_expired_user(user)

    async def keep_alive(self):
        self.alive_counter += 1
        if self.alive_counter < 60*15:
            return
        self.reset_alive_counter()
        try:
            logger.info("keep alive")
            async with self.lock:
                await self.page.goto("https://chat.openai.com/chat", timeout=60*1000)
            if self.standby:
                try:
                    msg = auto_send_messages[random.randint(0, len(auto_send_messages) - 1)]
                    async for msg in self.send_message('main', msg):
                        logger.info(msg)
                        break
                    self.standby = False
                except Exception as e:
                    logger.exception(e)
        except Exception as e:
            logger.exception(e)

    async def on_response(self, response):
        url = response.url
        if not (url.endswith('.otf') or url.endswith('.js')):
            logger.info(f"Response: {url} {response.status}")
        if url.endswith("api/auth/session"):
            if response.status == 200:
                body = await response.json()
                logger.info(f"body: {body}")
                if body:
                    self.access_token = body["accessToken"]
                    logger.info("++++=access token: %s", self.access_token)

    async def init(self):
        asyncio.create_task(self.heart_beat())

        BROWSER = await self.PLAY.firefox.launch_persistent_context(
            user_data_dir=f"/tmp/playwright/firefox-{self.user}",
            headless=False
        )

        self.page = await BROWSER.new_page()
        self.page.on('response', self.on_response)

        await async_stealth(self.page, pure=False)

        try:
            await asyncio.sleep(2.0)
            await self.page.goto("https://chat.openai.com/chat", timeout=60*1000)

            for _ in range(15):
                if self.access_token:
                    return
                await asyncio.sleep(1.0)

            logger.info("++++get_access_token")
            if await self.get_access_token():
                return

            await self.page.locator("button", has_text="Log in").click(timeout=15*1000)

            username = self.page.locator('input[name="username"]')
            await username.fill(self.user)
            await username.press("Enter")

            password = self.page.locator('input[name="password"]')
            await password.fill(self.password, timeout=600000)
            await password.press("Enter")
            
            # On first login
            next_button = self.page.locator("button", has_text="Next")
            await next_button.click()
            next_button = self.page.locator("button", has_text="Next")
            await next_button.click()
            next_button = self.page.locator("button", has_text="Done")
            await next_button.click()
        except Exception as e:
            logger.exception(e)

        while not self.access_token:
            logger.info("waiting for access token")
            await asyncio.sleep(2.0)

    async def get_access_token(self):
        if self.access_token:
            return True
        try:
            script = '''
            async ({}) => {
                console.log("fetch access token");
                const res = await fetch('https://chat.openai.com/api/auth/session', {method: 'GET'});
                console.log(res);
                if (!res.ok) {
                    console.log("++++++++status text:", res.statusText);
                    return {status: false, result: await res.statusText};
                }
                return {status: true, result: await res.json()};
            }
        '''
            ret = await self.page.evaluate(script, {})
            logger.info("++++++ret: %s", ret)
            if not ret['status']:
                return False
            if 'error' in ret and ret['error']:
                return False
            result = ret['result']
            if not result:
                return False
            self.access_token = result['accessToken']
            return True
        except Exception as e:
            logger.exception(e)
        return False

    async def reload(self):
        await self.page.reload()

    def get_user(self, user_id):
        if user_id in self.users:
            user = self.users[user_id]
        elif user_id in self.expired_user:
            user = self.expired_user[user_id]
            del self.expired_user[user_id]
            self.users[user_id] = user
        else:
            user = ChatGPTUser(user_id)
            self.users[user_id] = user
        user.reset_expiration()
        return user

    async def send_message(self, user_id, message):
        try:
            async with self.lock:
                user = self.get_user(user_id)
                self.busy = True
                async for msg in self._send_message(user, message):
                    yield msg
        finally:
            self.busy = False
        return

    async def _send_message(self, user, message):
        message_id = str(uuid.uuid4())
        if not user.parent_message_id:
            user.parent_message_id = str(uuid.uuid4())

        parser = MessageParser()

        logger.info("++++++message_id: %s, parent_message_id: %s", message_id, user.parent_message_id)
        body = {
            "action": "next",
            "messages": [
                {
                    "id": message_id,
                    "role": 'user',
                    "content": {
                        "content_type": 'text',
                        "parts": [message]
                    }
                }
            ],
            "model": 'text-davinci-002-render',
            "parent_message_id": user.parent_message_id
        }

        if user.conversation_id:
            body['conversation_id'] = user.conversation_id

        url = "https://chat.openai.com/backend-api/conversation"

        script = '''
        async ({ url, body, accessToken }) => {
            console.log(url, body, accessToken);
            const res = await fetch(url, {
            method: 'POST',
            body: body,
            signal: null,
            headers: {
                accept: 'text/event-stream',
                'x-openai-assistant-app-id': '',
                authorization: `Bearer ${accessToken}`,
                'content-type': 'application/json'
            }
            });
            console.log(res);
            if (!res.ok) {
                console.log("++++++++status text:", res.statusText);
                return res.text();
            }

            const reader = res.body.getReader()
            window.reader = reader
            window.result = res;
            return "OK";
            return await res.text();
        }
    '''
        ret = await self.page.evaluate(script, { 'url': url, 'body': json.dumps(body), "accessToken": self.access_token })
        logger.info("+++++++++ret: %s", ret)
        if not ret == "OK":
            await self.reload()
            detail = None
            try:
                detail = json.loads(ret)
            except Exception as e:
#                logger.exception(e)
                pass

            if detail:
                if 'Rate limit reached' in detail['detail']['message']:
                    self.standby = True
                    raise ChatGPTException(ret)
            if 'Too many requests' in ret:
                self.standby = True
                raise TooManyRequestsException(ret)
            raise ChatGPTException(ret)
        yield "[BEGIN]\n"
        done = False
        buffer = b''
        while not done:
            ret = await self.page.evaluate("""async () => {
                const { done, value } = await window.reader.read();
                // console.log(done, value);
                const hexValue = Array.from(value).map((i) => ('0' + i.toString(16)).slice(-2)).join('');
                return hexValue;
            }
            """, {})
            buffer += bytes.fromhex(ret)
            messages = buffer.split(b'\n\n')
            buffer = messages[-1]
            messages = messages[:-1]
            for msg in messages:
                if not msg:
                    continue
                msg = msg[len(b'data: '):]
                if b'[DONE]' in msg:
                    done = True
                    break
                msg = json.loads(msg)
                user.conversation_id = msg['conversation_id']
                user.parent_message_id = msg['message']['id']
                parser.feed(msg['message']['content']['parts'][0])
                message = parser.get_message()
                if message:
                    logger.info("++++++message %s", message)
                    yield message
                else:
                    await asyncio.sleep(0.0)
        message = parser.get_remanent_message()
        if message:
            logger.info("++++++last message: %s", message)
            yield message
        self.reset_alive_counter()
        self.users[user.user_id] = user
        return

async def run():
    bot = ChatGPTBot('usr', 'psw')
    await bot.init()
    question = "hello, will openai do evil things?"
    question = 'write a http server in python, demand: 1. use fastapi and uvicorn 2. can process post and get request 3. handle unexpected exception'
    async for msg in bot.send_message(question):
        print(msg)

if __name__ == "__main__":
    asyncio.run(run())
