import json
import os
import tomllib
from pathlib import Path

root = Path(__file__).resolve().parents[2]
with (root / 'pyproject.toml').open('rb') as metadata:
    version = tomllib.load(metadata)['project']['version']

docs = root / 'docs'
releases = json.loads((docs / 'versions.json').read_text(encoding='utf-8'))
if not releases or releases[0] != version:
    raise SystemExit(f'Put documentation release {version} first in docs/versions.json.')

english = docs / 'versioned_docs' / f'version-{version}'
russian_docs = docs / 'i18n' / 'ru' / 'docusaurus-plugin-content-docs'
russian = russian_docs / f'version-{version}'
sidebar = docs / 'versioned_sidebars' / f'version-{version}-sidebars.json'
if not sidebar.is_file() or not sidebar.stat().st_size:
    raise SystemExit(f'Missing required release documentation: {sidebar.relative_to(root)}')

english_articles = {
    file.relative_to(english) for file in english.rglob('*') if file.is_file() and file.suffix in {'.md', '.mdx'}
}
russian_articles = {
    file.relative_to(russian) for file in russian.rglob('*') if file.is_file() and file.suffix in {'.md', '.mdx'}
}
if not english_articles or english_articles != russian_articles:
    raise SystemExit(f'English and Russian documentation for release {version} must contain the same articles.')

tag = os.environ.get('RELEASE_TAG', '')
if tag and tag not in {version, f'v{version}'}:
    raise SystemExit(f'Release tag {tag} must match package and documentation version {version}.')

print(f'Package and bilingual documentation versions match: {version}')
