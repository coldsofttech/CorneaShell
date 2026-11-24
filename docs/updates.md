# Auto-update

How to let a Cornea app update itself: check a source for a newer version, download it, verify it, and restart into it. The page sees each step as an event.

What was tested here: the sources, download, checksum and signature checks, unpacking, and the helper script's text, on Linux against a local web server. Running the helper and restarting a real program are Windows steps and were **not** tested in this repository, so try a full update on a Windows machine before you ship.

## 1. Pick a source

A source answers one question: what is the newest release, and where is its file? Cornea ships three.

| Source | Use it for |
| --- | --- |
| `JsonFeed(url)` | Any web host, your own server, S3 or a static site. |
| `GitHubRelease("owner/name", asset="*-win64.zip")` | An app whose releases are on GitHub. |
| `Custom(function)` | Anything else: an internal API, a share, a database. |

```python
from cornea import GitHubRelease, JsonFeed, Custom, Release

JsonFeed("https://example.com/myapp/latest.json")
GitHubRelease("acme/myapp", asset="MyApp-*-win64.zip")
Custom(lambda: Release("2.1.0", "https://example.com/MyApp-2.1.0.zip", sha256="..."))
```

### The JSON feed

One object. `version` and `url` are needed. A relative `url` is resolved against the feed's own address.

```json
{
  "version": "1.4.0",
  "url": "MyApp-1.4.0-win64.zip",
  "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "signature": "base64...",
  "notes": "Faster start-up.",
  "size": 48213991,
  "min_version": "1.0.0"
}
```

`min_version` is the oldest version that may update straight to this one; an older app gets a clear error instead of a broken update.

### GitHub releases

`asset` is a file-name pattern, and exactly one asset must match it. The checksum comes from the asset's own GitHub digest, or from a `<name>.sha256` file next to it. A `<name>.sig` file is the signature for signed updates. Drafts are skipped, and pre-releases only count with `prerelease=True`. `token=` only raises GitHub's rate limit for the check.

### Your own source

Return a `Release`, a dict with the same keys as the feed, or `None` when there is nothing new. Any other exception becomes an `UpdateError`.

### What every source must satisfy

Addresses must be `https` with no login in them. Plain `http` is accepted only for this machine (`localhost`), for tests. A redirect to plain `http` is refused. Pass `allowed_hosts=("downloads.example.com",)` to the updater to also pin where files may come from.

## 2. Add the updater to your shell

```python
from cornea import Shell, Static, Updater, JsonFeed, App

shell = Shell(
    Static("web"),
    identity=App(id="com.example.myapp"),
    update=Updater(
        JsonFeed("https://example.com/myapp/latest.json"),
        current_version="1.3.0",
        check_on_start=True,
    ),
)
shell.run()
```

`current_version` is your app's own version (Cornea cannot know it). Nothing is checked, sent or downloaded unless you pass an updater. Downloads go under `%LOCALAPPDATA%\Cornea\<app id>\updates`, or `download_dir=` if you set it.

Drive the steps from Python when you want your own flow:

```python
release = shell.updater.check()          # Release or None
if release:
    shell.updater.download()             # verified file
    shell.updater.install()              # restarts the app
```

`update()` does all three.

## 3. Verify what you download

Two layers, both checked **before** anything is installed. A file that fails is deleted.

- **Checksum.** If the source gives a `sha256`, the download must match it. This is on by default and a release without one is refused (`require_hash=False` to allow it). A checksum served next to the file catches a damaged download, not a malicious one: anyone who can change your feed can change both.
- **Signed updates.** Pass `public_key=` and every release must carry a `signature` that this key accepts. Anything else is refused, so a hacked feed or file host cannot push code to your users.

```python
Updater(JsonFeed(...), current_version="1.3.0", public_key="<base64 Ed25519 public key>")
```

The extra package comes with `pip install "cornea-shell[signed-updates]"`.

Make a key pair once, keep the private key off the servers, and embed the public key in your app:

```python
import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

private = Ed25519PrivateKey.generate()
print(base64.b64encode(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode())
```

Sign each release file's **raw SHA-256 digest** (32 bytes), and put the base64 of the result in `signature`:

```python
import base64, hashlib
digest = hashlib.sha256(open("MyApp-1.4.0-win64.zip", "rb").read()).digest()
print(base64.b64encode(private.sign(digest)).decode())
```

## 4. What gets installed

| File type | What happens |
| --- | --- |
| `.zip` | Unpacked to a staging folder (paths that climb out are refused), then copied over the program's folder. If the zip wraps everything in one folder, that folder's content is used. |
| `.exe` | Run as an installer after the app exits. Give silent switches with `installer_args=("/SILENT",)`. |
| `.msi` | Run with `msiexec /i ... /qb`, plus `installer_args`. |

A running Windows program cannot replace its own files, so Cornea writes a small batch file, starts it detached, and closes the app. The batch file waits for the app's process to end, copies the files (or runs the installer), starts the new version with the same arguments, and deletes itself.

For a zip, the folder to replace is the packaged program's own folder. From source (not frozen) there is no such folder, so pass `install_dir=`. A path or argument that contains `" % ^ & | < > !` or a control character is refused, because a batch file cannot quote it safely. The program folder must be writable by the person running the app: an app in `Program Files` needs an installer (`.exe` or `.msi`) that asks for permission, not a zip.

## 5. Events and the page

The page hears each step as a `cornea:update-*` event on `window`:

| Event | Detail |
| --- | --- |
| `update-checking` | none |
| `update-none` | `{version}`: already up to date |
| `update-available` | `{version, notes, size, min_version}` |
| `update-progress` | `{received, total, percent}` (`total` and `percent` can be `null`) |
| `update-verified` | the release, once checked |
| `update-ready` | `{version}`: the app is about to close and restart |
| `update-error` | `{stage, message}`; `stage` is `check`, `download`, `verify` or `install` |

```js
window.addEventListener("cornea:update-progress", (e) => bar.value = e.detail.percent ?? 0);
```

A page that loads after an event was sent does not hear it. With `check_on_start=True` the check runs in the background right after the server starts, so ask for the result with `update_status`.

### Letting the page start the steps

Off by default. `Updater(page_control=True)` adds four native actions: `update_status`, `check_update`, `download_update` and `install_update`. They take no arguments, so the page can only run the steps for the source **you** configured; it cannot pick a URL or a file.

```js
const release = await cornea.call("check_update");
if (release) { await cornea.call("download_update"); await cornea.call("install_update"); }
```

`install_update` closes the app. Hold the window open with a [close guard](api.md#shell) while work is unsaved, or ask the person first.
