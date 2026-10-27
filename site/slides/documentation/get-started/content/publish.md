Vividly presentations are [single page](https://en.wikipedia.org/wiki/Single-page_application) [static web apps](https://en.wikipedia.org/wiki/Static_web_page) and can be hosted by any static web hosting providers.

In this tutorial we'll publish your slide to GitHub Pages. You'll need a GitHub account with Git credentials configured. 

### 1. GitHub repo

Create an empty repository on GitHub first—without a README, license, or .gitignore.

Initialize your repo and connect it to GitHub:

```sh
git init -b main
git remote add origin https://github.com/YOUR-NAME/YOUR-REPO.git

```

### 2. Configure the publishing target

Ask your agent to help with the next stage:

```text
Help me share this presentation on GitHub Pages.
```
It should create **vividly.publish.yaml** at the project root that looks something like: 

```yaml
schema: 1
targets:
  pages:
    provider: github-pages
    remote: origin
    branch: gh-pages
    expected_url: https://YOUR-NAME.github.io/YOUR-REPO/
```

Note that `expected_url` is reporting metadata, not a setting that creates the site. You only need to do this step once when configuring your workspace.

### 3. Commit your presentation

Stage, commit and push your changes:

```sh
git add vividly.yaml vividly.publish.yaml site .github .gitignore
git commit -m "Create my first Vividly slide"
git push -u origin main
```

### 4. Check, then publish

```sh
git status --short
vividly publish --dry-run
vividly publish
```

The status output must be empty. Publishing requires the **whole containing repository** to be clean and on an attached branch.

The publish command pushes the static site to `gh-pages`; it does not switch your working branch. If anything fails, read its diagnostic rather than forcing a push.

### 5. Enable Pages and open your slide

Once the first publication creates `gh-pages`, open your repository's **Settings > Pages**. Choose **Deploy from a branch**, select **gh-pages**, choose **/ (root)**, and save. For future publications, this setting is already in place.

Wait for GitHub Pages to deploy. Open the address reported by GitHub, then append:

```text
#/vividly/growth
```

Test the link in a private browser window. A successful push does not mean the Pages deployment has finished.

## Where next?

- [Follow a richer agent session](#/documentation/agent-session).
- [Make the design your own](#/documentation/customize).
- [Explore the documentation](#/documentation/overview).

For custom domains, existing repositories, and recovery, see the [publishing reference](#/documentation/publishing).
