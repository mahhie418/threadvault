# Registering the GitHub App

ThreadVault writes the vault through a GitHub App that you register for yourself. The app needs no private key and no client secret: it connects your GitHub account with the device flow.

## Register the app

1. On GitHub, open **Settings → Developer settings → GitHub Apps → New GitHub App**. To keep the vault in an organisation, register the app in the settings of that organisation instead.
2. Fill in **GitHub App name** with any name, and **Homepage URL** with any address, such as that of the vault.
3. Under **Identifying and authorizing users**:
   - Keep **Expire user authorization tokens** ticked. ThreadVault refreshes the tokens by itself.
   - Tick **Enable Device Flow**.
   - Leave **Callback URL** empty.
4. Under **Webhook**, untick **Active**.
5. Under **Permissions → Repository permissions**, select:
   - **Contents**: Read and write.
   - **Metadata**: Read-only. GitHub sets this by itself.
   - **Administration**: Read and write, only if ThreadVault should create the repository of the vault. Otherwise leave it at No access and create the repository yourself, because this permission also allows deleting repositories.
6. Under **Where can this GitHub App be installed?**, select **Only on this account**, unless the vault belongs to another account.
7. Select **Create GitHub App**.

## Note the Client ID and the app slug

On the page of the app:

- The **Client ID** goes to `GITHUB_APP_CLIENT_ID`.
- The app slug is the last part of the public link of the app, `https://github.com/apps/<slug>`, and goes to `GITHUB_APP_SLUG`.

ThreadVault needs neither a private key nor a client secret. If GitHub asks for a private key before it lets you install the app, generate one and delete it straight away; GitHub keeps only its public half.

## Install the app

Select **Install App** and the account that keeps the vault. Select the repository of the vault, or **All repositories**. A repository that ThreadVault creates joins the installation by itself.

## Connect your GitHub account

Run:

```
threadvault connect
```

The command shows a code and the page where you enter it. Once you approve, it saves the tokens, encrypted, in the data directory and prints the GitHub account that it connected.
