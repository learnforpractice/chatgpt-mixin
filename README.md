[![PyPi](https://img.shields.io/pypi/v/chatgpt-mixin.svg)](https://pypi.org/project/chatgpt-mixin)
[![PyPi](https://img.shields.io/pypi/dm/chatgpt-mixin.svg)](https://pypi.org/project/chatgpt-mixin)

# chatgpt-mixin

![Demo](./images/demo.png)

Demo bot: 7000101691

# Installation

on unix like platform, install `chatgpt-mixin` with the following command:

```bash
python3 -m pip install -U chatgpt-mixin
```

on the Windows platform, use the following command to install `chatgpt-mixin`:

```bash
python -m pip install -U chatgpt-mixin
```

Install chatgpt-mixin with the support of accessing openai model in a browser:

```bash
python3 -m pip install -U chatgpt-mixin[browser]
playwright install firefox
```

# configuration

First, you need to create a mixin bot from [developers.mixin.one](https://developers.mixin.one/dashboard).
And then under the `Secret` tab, click `Ed25519 session` to generate an App Session configuration.

To get started, you will need at least one ChatGPT account. If you don't have one already, you can create an account at [chat.openai.com](https://chat.openai.com/chat). Additionally, you can create an api key at [platform.openai.com/account/api-keys](https://platform.openai.com/account/api-keys)." 

After that, you can start this bot with the following command:

```bash
python3 -m chatgpt_mixin bot-config.yaml
```

which bot-config.yaml contains mixin bot configuration and chatgpt accounts as shown below.

```yaml
bot_config:
  pin: ""
  client_id: ""
  session_id: ""
  pin_token: ""
  private_key: ""
openai_api_keys: []
accounts:
 - user: ""
   psw: ""
```

`bot_config` section specify mixin bot configure. `openai_api_keys` section specify openai api keys. `accounts` section specify chatgpt test accounts. `user` field can not be empty, but you can leave `psw` to empty. If it is left empty, the user will need to manually enter the password upon login. Multiple accounts can be specified in the accounts section to improve ChatGPT responses. You can leave `accounts` section to empty if you only need to access openai models with `openai_api_keys`.

If you are running a bot of accessing model via browser in a server, you need to install `Xvfb` on the server, and use `VNC` at the client side to connect to `Xvfb`. For more information, refer to [Remote_control_over_SSH](https://en.wikipedia.org/wiki/Xvfb#Remote_control_over_SSH).


On the first time you start this bot, automated processes such as auto-filling of account names and passwords will be carried out, but you will still need to manually solve CAPTCHAs during the login process.


# Helpfull Commands

This is a list of helpful commands to use with the bot.

## /role

The `/role` command is used to get or set the role of the bot.

### Set role

To set the role of the bot, use the following format:

Usage:
```
/role <role description>
```

Example:
```
/role You are a helpful assistant
```

### Get role

To get the current role of the bot, use the following command:

```
/role
```

The bot will respond with the current role.

## /reset_role

The `/reset_role` command is used to reset the role of the bot to the default role.

Usage:
```
/reset_role
```

## /reset

The `/reset` command is used to clear the context of the bot.

Usage:
```
/reset
```

These commands should help you better interact with the bot.


# Acknowledgements

- [chatgpt-api](https://github.com/transitive-bullshit/chatgpt-api)
- [chatGPT-telegram-bot](https://github.com/altryne/chatGPT-telegram-bot)
- [ChatGPT](https://github.com/ChatGPT-Hackers/ChatGPT)
