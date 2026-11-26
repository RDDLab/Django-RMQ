# Deploy the Django-RMQ documentation

Pushes to any branch and pull requests run security checks. On `main`, a single
push workflow runs security checks followed by testing. Other protected branches
start testing for the current branch head after a successful push scan. To deploy,
run **Documentation** on `main` or dispatch it from another workflow.
The release workflow dispatches it after PyPI accepts the package. It
passes the release commit, which must belong to `main`. A manual run
without a commit deploys the `main` revision selected at launch.

```sh
gh workflow run docs.yml --repo RDDLab/Django-RMQ --ref main
```

To retry a specific revision, pass `-f source_sha=<full-commit-sha>`.
GitHub Actions builds the documentation image from the selected revision. Both documentation
deployment and PyPI publishing require security and test checks for the exact
revision. The separate **Security checks** workflow runs Gitleaks, Python and
Django SAST and dependency checks, JavaScript and TypeScript SAST and npm
audit, then checks GitHub Actions. The verification job checks the result of
a successful CI or testing run on `main` for that SHA after scanning.
Publish the current head of `main` after its tests succeed. Check the
**Documentation** run for the deployment result.

### PyPI Trusted Publishing

Configure the PyPI trusted publisher for organization `RDDLab`, repository
`Django-RMQ`, workflow file `publish.yml`, and GitHub Environment
`pypi`. Protect that environment with approved release tags and required
reviewers. Permit `main` if you use manual publishing from it.

### GitHub secrets and variables

In **Settings → Environments**, create `docs-production`. Under
**Deployment branches and tags**, choose **Selected branches and tags**
and add the branch `main`. Add these five **Environment secrets**.

| Secret | Value |
|---|---|
| `SSH_HOST` | The server hostname or IP, without a scheme or port |
| `SSH_PORT` | The SSH port, for example `22` |
| `SSH_PRIVATE_KEY` | The entire dedicated private key, with line breaks and both delimiters |
| `SSH_USER` | Account authorised to deploy the documentation |
| `SSH_HOST_KEY` | Server's ED25519 public host key |

Set this **Environment variable**.

| Variable | Value |
|---|---|
| `DOCS_IP` | Free static IPv4 address for this site on the existing Docker network `docs_net` |

Assign each site its own `DOCS_IP`.
Set `SSH_USER` to the existing deployment account, for example `deploy`. For `SSH_HOST_KEY`, use the first two
fields of the server's `/etc/ssh/ssh_host_ed25519_key.pub`, for example
`ssh-ed25519 AAAA…`. Obtain the key through the server console or its
administrator. From the server console, print the two fields with:

```sh
awk '{print $1, $2}' /etc/ssh/ssh_host_ed25519_key.pub
```

The workflow derives the host and port in `known_hosts`
from the two secrets.

Generate a dedicated ED25519 key without a passphrase for this unattended
job. Install its public half on the server. To upload the private half
without pasting it into a shell command, use GitHub CLI.

```sh
ssh-keygen -t ed25519 -f ./rmq-docs-ci -C django-rmq-docs-ci
gh secret set SSH_PRIVATE_KEY --env docs-production --repo RDDLab/Django-RMQ < ./rmq-docs-ci
```

### Server preparation and deployment

Use an existing unprivileged account that can execute commands over SSH and
access Docker with Compose V2. Bash, tar, and flock must be available on the host.
The existing GitHub Actions key can use the `restrict` option in
`~/.ssh/authorized_keys`. Use a key that can execute the workflow's SSH
commands. For a key previously configured with `command=`, use a dedicated
key without that option for both preparation and deployment.

After the checks succeed, the preparation job in `docs.yml` reads the
`docs-production` secrets directly. It sends the deployment script and
Compose files over SSH and installs them together under
`$HOME/.local/share/django-rmq-docs/<workflow-sha>/`. Repeating the
preparation for the same revision reuses the installed files. To prepare
the server by itself, run **Prepare documentation server** from `main`.

The documentation workflow uses the organization’s self-hosted Linux X64 runners.
Share a runner from the organization’s `Default` group with this repository.
The runner must have Docker with Compose V2, Git, an SSH client, `flock`, tar, and gzip.
The workflow provisions Go and downloads ShellCheck and jq when needed. The test gate uses the GitHub API.
Preparation verifies the serving host architecture. The runner builds both locales into an image and
streams the compressed Docker image over SSH.
The SSH account loads the image, verifies its commit and workflow run, and starts the container with its existing
Docker context or socket. When a rootless socket is available and no custom Docker context
is selected, the script uses that socket. Both SSH jobs use the existing account's permissions.

Connect the HTTPS reverse proxy for `django-rmq.rdd-lab.com` to the existing `docs_net` network
and use `http://<DOCS_IP>:8080` as its upstream. Port `8080` is internal to the container.
The static address must be available in that network’s IPv4 subnet.

The deployment lock serializes updates. The container checks both `/`
and `/ru/`. If the new deployment fails, the script restores the previous
image at its previous address on `docs_net` and reports a failed run. If the previous container
had no address on that network, the script uses the configured `DOCS_IP`.
To roll back a healthy deployment, dispatch the workflow with a previously deployed commit.
The workflow uses the current `DOCS_IP` for that deployment.

The runner builds from a source archive. The sitemap uses Git dates when built from a full checkout.

### Container build

The Dockerfile has three stages. `dependencies` uses Node.js 24.22.3 LTS,
installs the npm version pinned in `docs/package.json`, and installs
dependencies from the lockfile. `site-build` copies the documentation
sources and builds both locales. `runtime` copies the generated files and
Angie configuration into the official Angie 1.12.5 minimal image.

Run the build from the repository root.

```sh
docker build --file .github/docs/Dockerfile --tag django-rmq-docs:local .
```

Angie runs as the `angie` user with a read-only root filesystem under Compose.
It stores its PID and temporary files in the `/tmp` mount and writes
access and error logs to stdout and stderr.
