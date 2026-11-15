# Adam Dittrich — academic website

Version 4, deployed from the existing Quarto source project on 22 October 2026.

## Editing and publishing

Edit the `.qmd` files and commit to `main`. The existing **Publish Quarto website** workflow renders the site into `docs/`, validates its pages, internal links, assets and search index, and publishes that output to GitHub Pages. No manual ZIP upload or Pages-settings change is needed when editing through the connected repository.

| Content | Source |
|---|---|
| Homepage | `index.qmd` |
| Research | `research.qmd` |
| Publications and presentations | `publications.qmd` |
| Datasets | `data.qmd` |
| Teaching | `teaching.qmd` |
| Web CV | `cv.qmd` |
| Contact | `contact.qmd` |
| Styling | `assets/css/site-v4.css` and `assets/css/theme.scss` |
| Downloadable CV | `assets/files/Adam-Dittrich-CV.pdf` |
| Bibliography | `assets/files/publications.bib` |

## Version 4

The display name is Adam Dittrich, without a degree suffix. The PhD remains in the CV's education section. The homepage is shorter; the decorative archival image, blue promotional panels and generic introductory slogans have been removed. Research, publications and datasets open directly with the relevant content. Earlier corrections to teaching dates, conference records, translations and dataset attribution are retained.

A real portrait has not yet been supplied. The homepage includes a commented portrait figure, but no visible placeholder or generated likeness. To add the portrait, save it as `assets/img/adam-dittrich-portrait.jpg`, uncomment the figure in `index.qmd`, and add its path to `project.resources` in `_quarto.yml`. Social cards intentionally have no decorative image until a suitable portrait is supplied.

## CV download

The source PDF at `assets/files/Adam-Dittrich-CV.pdf` includes the Cliometrica article published online on 15 November 2026, with its DOI and 2026 citation. The downloadable copy is published under `docs/assets/files/`. The legacy heading migration in `scripts/prepare_cv.py` applies only to the original October 2026 PDF and leaves the updated CV untouched.

## Checks and recovery

`python3 scripts/check_site.py` checks the rendered output. `scripts/after_render.py` invokes it automatically before deployment. The GitHub workflow is unchanged.

The branch `backup/pre-v4-2026-10-22` preserves the website before this update. Git history remains intact; no force-push is required.
