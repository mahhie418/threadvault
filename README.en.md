# ThreadVault

[日本語](https://github.com/mahhie418/threadvault/blob/main/README.ja.md)

ThreadVault backs up a Slack workspace to a private GitHub repository, called the vault. The vault keeps the workspace in the JSON format of Slack's export, and as Markdown transcripts that people and AI services can read.

ThreadVault runs on your own computer as an internal Slack app. It connects to Slack with Socket Mode, so it needs no public address, and it talks only to Slack and GitHub.

## What it backs up

- Messages, thread replies and reactions in the public channels that the bot is in, and in the private channels that it has been invited to. The bot can also join the public channels by itself before each backup.
- The users and the channels of the workspace.
- Attached files, up to the size that you set.

Direct messages and Slack Connect channels are not backed up.

## Requirements

- macOS or Windows. ThreadVault also runs on Linux, but setup does not register it to start at login there.
- [uv](https://docs.astral.sh/uv/), which installs ThreadVault and the Python that it needs.
- Git 2.31 or later.
- A Slack workspace where you can create and install an app.
- A GitHub account or organisation to keep the vault.

## Install

```sh
uv tool install threadvault
```

## Set up

```sh
threadvault setup
```

Setup walks you through four steps and writes your answers to the settings file:

1. **Slack app.** Open the link that setup shows to create the Slack app, whose settings are filled in from the manifest. Follow the numbered steps, then paste the Bot User OAuth Token and the App-Level Token.
2. **GitHub App.** Answer whether the vault is to belong to a GitHub organisation, then open the link to register the GitHub App, whose settings are also filled in. Tick Enable Device Flow, create the app, install it on the account that keeps the vault, and paste the Client ID and the app slug.
3. **Owner.** Paste the member ID of the person who owns ThreadVault in Slack. To copy it, open their profile in Slack and select ⋮ (More), then Copy member ID.
4. **Check and autostart.** Setup checks the settings, Slack and git, then offers to start the Slack app automatically when you log in.

To change an answer, run setup again. A question that already has an answer shows it in brackets, or shows `[keep current]` for a token; press Enter to keep it. [Creating the Slack app](https://github.com/mahhie418/threadvault/blob/main/docs/slack.md) and [Registering the GitHub App](https://github.com/mahhie418/threadvault/blob/main/docs/github.md) explain how to do the first two steps by hand.

## Connect GitHub and choose the destination

With the Slack app running, open ThreadVault in Slack and go to its Home tab:

1. Select **Connect GitHub**, open the page that it shows and enter the code.
2. Select **Choose destination** and then a private repository that the GitHub App can access, or select **Create new repository** in the same window to create a private one.
3. Select **Change settings** to set the time of the daily backup, the channels to back up, the attached files and the language of the Markdown.
4. Select **Back up now** and then **Start**, or wait for the daily backup.

Selecting **Whole history again** in **Back up now** fetches every channel again from the start. It deletes nothing from the vault.

## Owner and admins

- The owner can do everything, including allowing admins to operate the app with **Admin permissions** and handing the ownership to an admin with **Transfer ownership**. Setup writes the first owner to `THREADVAULT_OWNER_ID`.
- Admins allowed by the owner see the connection to GitHub and the destination. They can also connect GitHub, choose the destination, change the settings and start backups.
- Everyone else, including the other admins, sees only the status of the backups.

Setup does not ask for admins. To add them, write their member IDs to `THREADVAULT_ADMIN_IDS` in the settings file, separated by commas, then restart the Slack app:

```
THREADVAULT_ADMIN_IDS=U0123ABCDE,U0456FGHIJ
```

The owner and the admins allowed by the owner get a direct message when GitHub is connected or disconnected, when the destination changes and when a backup fails.

## Settings

ThreadVault reads `threadvault.env` in your configuration folder. Environment variables take precedence over the file.

| System | Settings file | Data folder |
|---|---|---|
| macOS | `~/Library/Application Support/threadvault/threadvault.env` | `~/Library/Application Support/threadvault` |
| Windows | `%LOCALAPPDATA%\threadvault\threadvault.env` | `%LOCALAPPDATA%\threadvault` |
| Linux | `~/.config/threadvault/threadvault.env` | `~/.local/share/threadvault` |

| Variable | Meaning |
|---|---|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token of the Slack app (`xoxb-…`) |
| `SLACK_APP_TOKEN` | App-Level Token of the Slack app (`xapp-…`) |
| `GITHUB_APP_CLIENT_ID` | Client ID of the GitHub App |
| `GITHUB_APP_SLUG` | App slug of the GitHub App |
| `THREADVAULT_OWNER_ID` | Member ID of the first owner |
| `THREADVAULT_ADMIN_IDS` | Member IDs of the admins, separated by commas |
| `THREADVAULT_DATA_DIRECTORY` | Folder for the database, the key and the working copies of the vault. Keep it on a local disk. |
| `THREADVAULT_SECRET_KEY` | Key that encrypts the GitHub tokens. `threadvault key` prints a new one. |
| `THREADVAULT_LANGUAGE_DISPLAY` | Language of App Home, `en` or `ja`, for people whose Slack language is neither English nor Japanese |
| `THREADVAULT_LOOKBACK_DAYS` | Number of recent days fetched again in every backup, from 1 to 90 |
| `THREADVAULT_DELETIONS_MAXIMUM` | Most messages that one backup may delete from the vault. A backup that would delete more deletes none, and `0` deletes nothing. |

Restart the Slack app after you change the settings file.

## Commands

| Command | What it does |
|---|---|
| `threadvault setup` | Creates the Slack app, registers the GitHub App, chooses the owner and starts the Slack app at login, writing the settings file |
| `threadvault start` | Runs the Slack app until it is stopped. `--log FILE` appends the output to a file. |
| `threadvault stop` | Stops the Slack app and stops it from starting at login (macOS) |
| `threadvault doctor` | Checks the settings, Slack, git, GitHub and the destination |
| `threadvault connect` | Connects GitHub from the terminal, as **Connect GitHub** does in App Home |
| `threadvault backup --out DIR` | Backs up the workspace once into a local folder |
| `threadvault backup --repo OWNER/NAME` | Backs up the workspace once into a GitHub repository, which is created as private when it is missing |
| `threadvault manifest` | Prints the manifest for creating the Slack app |
| `threadvault key` | Prints a new key for `THREADVAULT_SECRET_KEY` |

## Running ThreadVault

App Home and the daily backups work only while the Slack app runs. If setup registered it to start at login, it is already running, and it starts again whenever it stops with an error; its output goes to `start.log` in the data folder. Otherwise, run `threadvault start` and keep it running.

Run only one Slack app for a workspace. ThreadVault refuses to start twice with the same data folder, but if it ran on two computers, Slack would split the events and the button presses between them.

The daily backup needs the computer to be on. If it was asleep or off at that time, the backup runs soon after the Slack app runs again.

To restart the Slack app, for example after changing the settings file:

- macOS: `launchctl kickstart -k gui/$(id -u)/threadvault`
- Windows: `schtasks /End /TN threadvault`, then `schtasks /Run /TN threadvault`
- Without autostart: stop `threadvault start` with Ctrl+C and run it again.

To stop the Slack app and stop it from starting at login:

- macOS: `threadvault stop`
- Windows: `schtasks /End /TN threadvault` and `schtasks /Delete /TN threadvault /F`, then delete `threadvault.xml` in the data folder.

## Update and uninstall

To update ThreadVault, run `uv tool upgrade threadvault`, then restart the Slack app. When a new version changes the manifest, also update the Slack app as [Update the app](https://github.com/mahhie418/threadvault/blob/main/docs/slack.md#update-the-app) describes.

To uninstall ThreadVault, stop the Slack app and its start at login as above, or stop `threadvault start` with Ctrl+C, then run `uv tool uninstall threadvault`. The settings file and the data folder stay, so delete them if you no longer need them. The Slack app, the GitHub App and the vault stay too, until you delete them in Slack and GitHub.

## The vault

```
README.md                         Introduction, written once; edit it freely
.gitattributes
.threadvault/state.json           State of the backups
raw/                              The workspace in the JSON format of Slack's export
    users.json
    channels.json
    groups.json
    <channel>/<YYYY-MM-DD>.json   Messages of one day in UTC
transcripts/                      The messages as Markdown
    index.md                      Layout of the vault and list of the channels
    <channel>/<YYYY-MM>.md        Messages of one month, with thread replies under their parent
attachments/<YYYY-MM>/<file ID>/  Attached files, linked from the Markdown
```

The first backup of a channel fetches all of its history that Slack provides, and commits and pushes channel by channel. Later backups fetch the recent days again. They also catch replies to older threads and edits and deletions of older messages, which the Slack app records as they happen.

When a message disappears from Slack, the next backup removes it from the files of the vault, while the git history keeps it. Messages older than 83 days stay in the vault, so that messages that Slack no longer shows are not taken for deleted ones.

## Notes

- On the Free plan, Slack shows only the last 90 days of messages and deletes messages older than a year. The vault keeps what ThreadVault has backed up, so set it up early.
- The settings file holds the Slack tokens, and on macOS and Linux only you can read it. The GitHub tokens are stored encrypted in the data folder.
- ThreadVault backs up only to private repositories, and refuses public ones.
