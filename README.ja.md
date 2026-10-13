# ThreadVault

[English](README.en.md)

ThreadVault は、Slack のワークスペースを GitHub のプライベートリポジトリ (vault) にバックアップします。vault には、Slack のエクスポートと同じ形式の JSON と、人や AI サービスが読みやすいように Markdown にした会話の記録が入ります。

ThreadVault は、あなたのコンピューターで、ワークスペース内だけで使う Slack app として動きます。Slack とは Socket Mode でつながるので外部に公開する URL は要らず、通信先は Slack と GitHub だけです。

## バックアップするもの

- bot が参加している公開チャンネルと、bot を招待したプライベートチャンネルのメッセージ、スレッドの返信、リアクション。バックアップの前に、bot が公開チャンネルに自動で参加するようにもできます。
- ワークスペースのユーザーとチャンネルの情報。
- 添付ファイル (設定した上限まで)。

DM と Slack Connect のチャンネルはバックアップしません。

## 必要なもの

- macOS か Windows。Linux でも動きますが、setup でログイン時の自動起動は登録できません。
- [uv](https://docs.astral.sh/uv/) (ThreadVault と、その実行に必要な Python をインストールします)。
- Git 2.31 以上。
- Slack app を作成してインストールできるワークスペース。
- vault を置く GitHub のアカウントまたは Organization。

## インストール

```sh
uv tool install threadvault
```

## 初期設定

```sh
threadvault setup
```

setup は次の 4 つの段階を順に案内し、入力した内容を設定ファイルに保存します。

1. **Slack app**: setup が表示するリンクを開いて Slack app を作成します。設定は manifest から自動で入力されます。表示される手順に従って進め、Bot User OAuth Token と App-Level Token を貼り付けます。
2. **GitHub App**: vault を GitHub の Organization に置くかどうかに答えてから、リンクを開いて GitHub App を登録します。こちらも設定は自動で入力されます。Enable Device Flow にチェックを入れて GitHub App を作成し、vault を置くアカウントにインストールしてから、Client ID と app slug を貼り付けます。
3. **オーナー**: Slack で ThreadVault のオーナーにする人のメンバー ID を貼り付けます。メンバー ID は、Slack でその人のプロフィールを開き、⋮ (その他) の「メンバー ID をコピー」でコピーできます。
4. **確認と自動起動**: 設定、Slack、git を確認してから、ログイン時に Slack app を自動で起動するかどうかを聞きます。

設定を変えるときは、setup をもう一度実行します。質問の後ろの [ ] に今の値が表示されているときは、Enter を押すとその値のまま進めます。Slack app を手動で作成する方法は [Creating the Slack app](docs/slack.md) に、GitHub App を手動で登録する方法は [Registering the GitHub App](docs/github.md) にあります (どちらも英語)。

## GitHub との連携と保存先

Slack app を動かした状態で、Slack で ThreadVault を開き、ホームタブを表示します。

1. 「GitHub と連携する」を選択し、表示されたページを開いてコードを入力します。
2. 「保存先を選ぶ」を選択して GitHub App がアクセスできるプライベートリポジトリを選ぶか、同じ画面の「新しいリポジトリを作成する」を選択してプライベートリポジトリを作成します。
3. 「設定を変更する」を選択して、毎日のバックアップの時刻、バックアップするチャンネル、添付ファイル、Markdown の言語を設定します。
4. 「今すぐバックアップ」を選択して「開始」を選択するか、毎日のバックアップを待ちます。

「今すぐバックアップ」で「全期間を再取得」を選択すると、すべてのチャンネルを最初から取得し直します。このとき vault から削除されるものはありません。

## オーナーと管理者

- オーナーはすべての操作ができます。「管理者の権限」で管理者に操作を許可したり、「オーナーの譲渡」で管理者にオーナーを譲ったりすることもできます。最初のオーナーは、setup が `THREADVAULT_OWNER_ID` に保存します。
- オーナーが許可した管理者は、GitHub との連携の状態と保存先を見られます。GitHub との連携、保存先の選択、設定の変更、バックアップの開始もできます。
- それ以外の人は、許可されていない管理者も含めて、バックアップの状態だけを見られます。

setup では管理者を設定しません。管理者を追加するときは、設定ファイルの `THREADVAULT_ADMIN_IDS` にメンバー ID をカンマ区切りで書き、Slack app を再起動します。

```
THREADVAULT_ADMIN_IDS=U0123ABCDE,U0456FGHIJ
```

GitHub との連携や解除、保存先の変更、バックアップの失敗は、オーナーと、オーナーが許可した管理者に DM で通知されます。

## 設定

ThreadVault は、設定フォルダの `threadvault.env` を読み込みます。同じ名前の環境変数があれば、そちらを優先します。

| OS | 設定ファイル | データフォルダ |
|---|---|---|
| macOS | `~/Library/Application Support/threadvault/threadvault.env` | `~/Library/Application Support/threadvault` |
| Windows | `%LOCALAPPDATA%\threadvault\threadvault.env` | `%LOCALAPPDATA%\threadvault` |
| Linux | `~/.config/threadvault/threadvault.env` | `~/.local/share/threadvault` |

| 変数 | 内容 |
|---|---|
| `SLACK_BOT_TOKEN` | Slack app の Bot User OAuth Token (`xoxb-…`) |
| `SLACK_APP_TOKEN` | Slack app の App-Level Token (`xapp-…`) |
| `GITHUB_APP_CLIENT_ID` | GitHub App の Client ID |
| `GITHUB_APP_SLUG` | GitHub App の app slug |
| `THREADVAULT_OWNER_ID` | 最初のオーナーのメンバー ID |
| `THREADVAULT_ADMIN_IDS` | 管理者のメンバー ID (カンマ区切り) |
| `THREADVAULT_DATA_DIRECTORY` | データベース、鍵、vault の作業用のクローンを置くフォルダ。ローカルディスク上に置いてください。 |
| `THREADVAULT_SECRET_KEY` | GitHub のトークンを暗号化する鍵。`threadvault key` で新しい鍵を作成できます。 |
| `THREADVAULT_LANGUAGE_DISPLAY` | Slack の言語が英語でも日本語でもない人に表示する App Home の言語 (`en` または `ja`) |
| `THREADVAULT_LOOKBACK_DAYS` | バックアップのたびに取得し直す直近の日数 (1〜90) |
| `THREADVAULT_DELETIONS_MAXIMUM` | 1 回のバックアップで vault から削除してよいメッセージの数の上限。これを超える場合は 1 件も削除せず、`0` のときは何も削除しません。 |

設定ファイルを変更したら、Slack app を再起動してください。

## コマンド

| コマンド | 内容 |
|---|---|
| `threadvault setup` | Slack app の作成、GitHub App の登録、オーナーの設定、ログイン時の自動起動の登録を案内し、設定ファイルに保存します |
| `threadvault start` | 止めるまで Slack app を実行します。`--log FILE` を付けると、出力をファイルに追記します。 |
| `threadvault doctor` | 設定、Slack、git、GitHub、保存先を確認します |
| `threadvault connect` | App Home の「GitHub と連携する」と同じ操作を、ターミナルから行います |
| `threadvault backup --out DIR` | ワークスペースを 1 回、ローカルのフォルダにバックアップします |
| `threadvault backup --repo OWNER/NAME` | ワークスペースを 1 回、GitHub のリポジトリにバックアップします (リポジトリがなければ、プライベートリポジトリとして作成します) |
| `threadvault manifest` | Slack app を作成するための manifest を表示します |
| `threadvault key` | `THREADVAULT_SECRET_KEY` 用の新しい鍵を作成して表示します |

## ThreadVault を動かす

App Home と毎日のバックアップは、Slack app が動いている間だけ動作します。setup でログイン時の自動起動を登録した場合は、すでに動いています。エラーで止まったときも自動で再起動し、出力はデータフォルダの `start.log` に書き込まれます。登録していない場合は、`threadvault start` を実行したままにしてください。

1 つのワークスペースに対して動かす Slack app は、1 つだけにしてください。同じデータフォルダで 2 つ目を起動しようとすると ThreadVault が止めますが、2 台のコンピューターで動かすと、Slack がイベントやボタンの操作を両方に振り分けてしまいます。

毎日のバックアップには、その時刻にコンピューターが起動している必要があります。スリープや電源オフの間に時刻を過ぎた場合は、Slack app が再び動き始めてからまもなくバックアップします。

Slack app を再起動するには (設定ファイルを変更したときなど):

- macOS: `launchctl kickstart -k gui/$(id -u)/threadvault` を実行します。
- Windows: `schtasks /End /TN threadvault` を実行してから、`schtasks /Run /TN threadvault` を実行します。
- 自動起動を使っていない場合: `threadvault start` を Ctrl+C で止めて、もう一度実行します。

ログイン時の自動起動をやめるには:

- macOS: `launchctl bootout gui/$(id -u)/threadvault` を実行して、`~/Library/LaunchAgents/threadvault.plist` を削除します。
- Windows: `schtasks /Delete /TN threadvault /F` を実行して、データフォルダの `threadvault.xml` を削除します。

## vault の中身

```
README.md                         説明 (最初に 1 回だけ作成。自由に編集可)
.gitattributes
.threadvault/state.json           バックアップの状態
raw/                              Slack のエクスポートと同じ形式の JSON
    users.json
    channels.json
    groups.json
    <channel>/<YYYY-MM-DD>.json   1 日分のメッセージ (UTC)
transcripts/                      Markdown にしたメッセージ
    index.md                      vault の構成とチャンネルの一覧
    <channel>/<YYYY-MM>.md        1 か月分のメッセージ (スレッドの返信は親メッセージの下)
attachments/<YYYY-MM>/<file ID>/  添付ファイル (Markdown からリンク)
```

チャンネルの最初のバックアップでは、Slack から取得できる限りの全履歴を取得し、チャンネルごとに commit して push します。2 回目以降は、直近の日数分を取得し直します。古いスレッドへの返信や、古いメッセージの編集・削除も反映します (Slack app の起動中に記録したものに限ります)。

Slack から削除されたメッセージは、次のバックアップで vault のファイルからも削除されます (git の履歴には残ります)。ただし、83 日より古いメッセージは vault に残します。Slack に表示されなくなっただけのメッセージを、削除されたものと取り違えないためです。

## 注意

- Slack のフリープランでは、直近 90 日のメッセージしか表示されず、1 年より古いメッセージは削除されます。ThreadVault でバックアップしたものは vault に残るので、早めに使い始めてください。
- 設定ファイルには Slack のトークンが含まれます。macOS と Linux では、本人だけが読めるように保存します。GitHub のトークンは、暗号化してデータフォルダに保存します。
- ThreadVault はプライベートリポジトリにだけバックアップし、公開リポジトリへのバックアップは行いません。
