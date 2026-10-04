# threadvault

この vault は、threadvault で作った Slack ワークスペースのバックアップです。形式のバージョン: 1

- `raw/` には、ワークスペースの内容が Slack のエクスポートと同じ JSON 形式で入っています。`users.json`、`channels.json`、`groups.json` はユーザーとチャンネルの情報で、チャンネルごとのディレクトリには、メッセージが UTC の 1 日ごとのファイルに入っています。
- `transcripts/` には、メッセージがチャンネルごと、1 か月ごとの Markdown で入っています。時刻は Asia/Tokyo で、スレッドの返信は親の下にあります。

## チャンネル

- [#general](general/)
- [#xxx](xxx/)
