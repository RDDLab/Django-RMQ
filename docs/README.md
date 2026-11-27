# Django RMQ documentation

Use Node.js from the repository's `.nvmrc` and the npm version in `package.json`.
Run `npm ci` from `docs/` before building or running the live preview with
`npm run docs:dev`.

## Publish documentation for a new version

Keep the English articles in `versioned_docs/version-VERSION/` and their
Russian counterparts in
`i18n/ru/docusaurus-plugin-content-docs/version-VERSION/`.
Save that version's navigation as
`versioned_sidebars/version-VERSION-sidebars.json`. Where the sidebar uses
translated labels, save them next to the Russian articles in
`version-VERSION.json`.

Put the desired default version first in `versions.json`. The site and local
preview serve it at `/docs/` and `/ru/docs/`. All other versions keep their
version-specific URLs. For each release, add its new files and leave the
previous version directories intact.

Run `npm run docs:build` before publishing. Publishing checks that
the release tag, the package version, and the first entry in `versions.json`
match, and that the release contains the same articles in both languages.

See the [deployment guide](../.github/docs/README.md) for GitHub Actions and server setup.
