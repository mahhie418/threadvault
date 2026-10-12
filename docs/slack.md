# Creating the Slack app

ThreadVault runs as a Slack app that you create in your own workspace from the manifest of ThreadVault. The app uses Socket Mode, so it needs no public address. `threadvault setup` opens the page to create the app with the manifest filled in; this page explains how to create the app by hand.

## Create the app

1. Run `threadvault manifest` and copy what it prints.
2. Open https://api.slack.com/apps, select **Create New App**, then **From a manifest**.
3. Select the workspace, then select **Next**.
4. On the **JSON** tab, replace the manifest with the one that you copied, then select **Next** and **Create**.

## Install the app

In **Basic Information**, select **Install to Workspace** and allow the access that the app asks for. If the workspace requires approval for apps, an admin of the workspace has to approve the app first.

## Note the tokens

- In **OAuth & Permissions**, the **Bot User OAuth Token**, which starts with `xoxb-`, goes to `SLACK_BOT_TOKEN`.
- In **Basic Information**, under **App-Level Tokens**, select **Generate Token and Scopes**. Name the token, add the `connections:write` scope and select **Generate**. The token, which starts with `xapp-`, goes to `SLACK_APP_TOKEN`.

## Note the owner

The member ID of the person who owns ThreadVault goes to `THREADVAULT_OWNER_ID`. To copy it, open their profile in Slack and select ⋮ (More), then **Copy member ID**.

Write these values to the settings file, as the README describes, or paste them when `threadvault setup` asks for them.

## Update the app

When a new version of ThreadVault changes the manifest, open **App Manifest** in the settings of the app, replace the manifest with what `threadvault manifest` prints, and select **Save Changes**. If Slack asks you to reinstall the app, reinstall it and allow the new access.
