# {product}

This vault is a backup of a Slack workspace, made by {product}. Format version: {version}.

- `{raw}/` holds the workspace in the JSON format of Slack's export: `{users}`, `{channels}` and `{groups}` describe the users and the channels, and each channel has a directory with its messages, one file a day in UTC.
- `{transcripts}/` holds the messages as Markdown, one file a month for each channel, with times in {timezone} and thread replies under their parent.

## Channels
