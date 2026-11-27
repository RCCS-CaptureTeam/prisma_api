# Guide pages

Task-based guides for prisma_api users, one Markdown file per topic, for example
`syncing-case-studies.md` or `publishing-datasets.md`. This README is a note for maintainers and
is not published.

The PrISMa platform shows these pages in its internal docs (API guide → prisma_api), together
with this repository's top-level `README.md` and a reference generated from the docstrings. The
platform pulls a copy with `python manage.py sync_api_docs ../prisma_api` from a clean, ideally
tagged, checkout. Edit the docs here, never the copies in prisma_cloud.

Conventions:

- Plain Markdown that reads well on GitHub. Optional front matter sets the nav title and
  position:

  ```yaml
  ---
  title: Syncing case studies
  order: 20
  ---
  ```

- Relative links to other guide pages, to `../../README.md` and to images in this repository
  keep working on the platform. Links to other files point at the synced commit on GitHub.
- Don't add an `index.md`: the top-level `README.md` is the section page.
- Docstrings: use Google style (`Args:`, `Returns:`, `Raises:`, `Examples:`) for new and changed
  functions. These sections become parameter tables in the generated reference.
