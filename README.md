# chatgpt-mixin

# Installation

on unix like platform, install `chatgpt-mixin` with the following command.

```bash
python3 -m pip install chatgpt-mixin
playwright install
```

on the Windows platform, use the following command to install `chatgpt-mixin`:

```bash
python -m pip install chatgpt-mixin
playwright install
```

# configuration

you can start this bot with the following command:

```bash
chatgpt-bot config.yaml
```

which config.yaml contains mixin bot configuration and chatgpt accounts as shown below.

```yaml
bot_config:
  pin: ""
  client_id: ""
  session_id: ""
  pin_token: ""
  private_key: ""
accounts:
 - user: ""
   psw: ""
```

`bot_config` section specify mixin bot configure. `accounts` section specify chatgpt test accounts. `user` field can not be empty, but you can leave `psw` to empty. you can specify multiple accounts in the `accounts` section.

on the first time you start this bot, some automation will performed by this bot, but you still need to solve CAPTCHAs manually during login. 
