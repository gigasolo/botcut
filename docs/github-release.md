# GitHub release

No release has been published. [gigasolo/botcut](https://github.com/gigasolo/botcut) is public, the default branch is `master`, and the Releases page is empty. This note is the procedure for a later release. It does not tag, build a package for upload, or run `gh release create`.

## What is packaged today

`./bin/install` is a local install on an Arch machine. It runs `./bin/build`, then `makepkg -fsi` in `pkgbuild/`. `-f` rebuilds even when `pkgver` did not change. `-s` installs missing build dependencies. `-i` installs the result on this machine and needs a password. That is not a GitHub release.

`pkgbuild/PKGBUILD` is `botcut` `0.1.0-1`. `source` is empty. `build()` leaves `pkgbuild/` and runs `./bin/build` in the repo checkout that contains it. The bytes in the package are whatever tree `makepkg` just compiled, including uncommitted files. `package()` installs four paths:

- `/usr/bin/botcut`
- `/usr/share/applications/botcut.desktop`
- `/usr/share/icons/hicolor/scalable/apps/botcut.svg`
- `/usr/share/licenses/botcut/LICENSE`

`*.pkg.tar.*` is gitignored. A package built in `pkgbuild/` stays on this machine. Do not commit it.

The package does not install `botcut-cli`. The window looks for `botcut-cli` on `PATH`. If that is missing, it looks for `uv` and `~/code/botcut/cli/pyproject.toml`, and runs `uv run --project ~/code/botcut/cli botcut-cli`. A person who only installs `/usr/bin/botcut` can trim a file. Spoken cuts, Change this cut, Make card, Captions, and Short stop with "botcut-cli was not found" unless that checkout is still on the machine.

`PKGBUILD` `depends` lists ffmpeg, Qt 6, and `xdg-desktop-portal`. The binary also links `libsecret-1` (`omacut.pro`). The README lists libsecret as a requirement. The package does not.

`botcut.desktop` claims the same video MIME types as stock Omacut. Both can offer to open the same file. The package does not conflict with, provide, or replace `omacut`.

`origin/master` does not contain the revise thread, the cards, or the keep-list watch. A package built from that commit is an older window. A release tag has to point at a commit that already contains the tree being shipped.

## What a release would attach

One asset: `botcut-<pkgver>-<pkgrel>-x86_64.pkg.tar.zst`, built from a clean checkout of the tag.

GitHub also adds source zip and tar.gz archives of that tag. Those are the repo, not a built package. Building them still needs Qt 6, a compiler, ffmpeg, and `./bin/build`. Spoken cuts still need `botcut-cli` on `PATH`.

Leave these off the release:

- `botcut-debug-*.pkg.tar.zst`, if `makepkg` emits one
- `local-shots/`, movies, and `cuts.json` from a real cut
- `XAI_API_KEY`, keyring exports, and anything under `~/.local/share/botcut`
- `cli/botcut.egg-info/`, `__pycache__/`, and `cli/uv.lock` if it is still untracked

Install from a downloaded asset, after the Arch dependencies are present:

```bash
sudo pacman -U botcut-<pkgver>-<pkgrel>-x86_64.pkg.tar.zst
```

`pacman -U` installs that file. It does not fetch the Qt and ffmpeg packages from the asset. Those come from the Arch repositories. `/usr/bin/botcut` is replaced. An already-open window keeps the binary it started with until it is quit.

## Before the first tag

1. Commit the tree that should ship. The tag has to be that commit, on `master`.
2. Set `pkgver` in `pkgbuild/PKGBUILD` and `version` in `cli/pyproject.toml` to the same number. Leave `pkgrel` at `1` for a new `pkgver`. Do not publish another `0.1.0-1` with different bytes. Machines that already installed `0.1.0-1` from `./bin/install` will treat that name as the package they have.
3. Put `libsecret` in `depends`.
4. Install `botcut-cli` into the package, on `PATH`, as `/usr/bin/botcut-cli`. The fallback to `~/code/botcut/cli` is this checkout, not a release layout. The command needs Python and `requests` (`python-requests` in `depends` is the Arch name). The wrapper can be a small script that runs the module from `/usr/share/botcut/cli`. Until that lands, the release notes have to say that spoken cuts need a separate `uv` checkout.
5. Point `source` at the tag archive when the PKGBUILD should build outside this checkout:

   `https://github.com/gigasolo/botcut/archive/refs/tags/v<pkgver>.tar.gz`

   `build()` then runs inside `$srcdir`, not `$startdir/..`. Fill in `sha256sums` for that archive. Until then, `makepkg` only works from a full clone with `pkgbuild/` inside it.

The desktop MIME overlap with Omacut can stay for the first release. A later package can narrow the types or add a conflict. Do not add one in the notes as if it already exists.

## Steps, when a release is wanted

Run these from a clean `git checkout` of the tag. Do not use `./bin/install`. That installs onto the build machine.

```bash
cd pkgbuild
makepkg -f --noconfirm
```

`-f` rebuilds the same `pkgver`. `--noconfirm` does not install. The package file appears next to the PKGBUILD and remains gitignored.

Confirm `pacman -Qip` on that file lists `/usr/bin/botcut` and, once the CLI is packaged, `/usr/bin/botcut-cli`. Confirm the archive contains no key and no movie.

Publish from the tag:

```bash
gh release create "v<pkgver>" \
  "pkgbuild/botcut-<pkgver>-1-x86_64.pkg.tar.zst" \
  --repo gigasolo/botcut \
  --title "BotCut <pkgver>" \
  --notes-file /tmp/botcut-release-notes.md
```

The notes say what changed since the previous tag, that the package is x86_64 Arch, and whether `botcut-cli` is inside it. They do not include an API key.

A later GitHub Actions workflow can run that `makepkg` in an `archlinux` container on the tag and upload the same asset. No workflow is in the repo. Adding one is part of doing the release, not part of this note.
