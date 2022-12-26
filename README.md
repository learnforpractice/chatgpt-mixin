# chatgpt-mixin

# Installation

on unix like platform, install `chatgpt-mixin` with the following command.

```bash
python3 -m pip install chatgpt-mixin
playwright install firefox
```

on the Windows platform, use the following command to install `chatgpt-mixin`:

```bash
python -m pip install chatgpt-mixin
playwright install
```

# configuration

you can start this bot with the following command:

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
accounts:
 - user: ""
   psw: ""
```

`bot_config` section specify mixin bot configure. `accounts` section specify chatgpt test accounts. `user` field can not be empty, but you can leave `psw` to empty. If it is left empty, the user will need to manually enter the password upon login. Multiple accounts can be specified in the accounts section to improve ChatGPT responses.

If you are running a bot in a server, you need to install `Xvfb` on the server, and use `VNC` at the client side to connect to `Xvfb`. For more information, refer to [Remote_control_over_SSH](https://en.wikipedia.org/wiki/Xvfb#Remote_control_over_SSH).


On the first time you start this bot, automated processes such as auto-filling of account names and passwords will be carried out, but you will still need to manually solve CAPTCHAs during the login process.

