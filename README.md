# Adam Dittrich, PhD — academic website

Revised **21 October 2026** for GitHub account `adamdittrich`.

## Update the existing website

Open the `adamdittrich.github.io` repository, choose **Add file → Upload files**,
and upload the files and folders **inside** the update package. Commit to
`main`. The existing **Publish Quarto website** workflow renders and deploys the
site. No new repository, Pages setting or publishing workflow is required.

Keep the directory structure: the revised CV is
`assets/files/Adam-Dittrich-CV.pdf`; styling is `assets/css/styles.css`.
Upload the `assets` folder rather than moving its files to the repository root.

## Editable pages

| Page | Source |
|---|---|
| Home | `index.qmd` |
| Research | `research.qmd` |
| Publications and presentations | `publications.qmd` |
| Data | `data.qmd` |
| Teaching | `teaching.qmd` |
| Web CV | `cv.qmd` |
| Contact | `contact.qmd` |

The downloadable public CV and bibliographic records are in `assets/files/`.
The teaching page lists courses and start dates without course-resource links.
Conference presentations and published proceedings are separate sections.
Czech titles are accompanied by bracketed English translations.

## Building and previewing

The production build is `quarto render`, with output in `docs/` as configured
in `_quarto.yml`. Only `.qmd` pages are rendered; these project instructions do
not become website pages. The source package need not contain generated HTML.

The optional `scripts/render_static.py` is a Pandoc preview helper, not the
production Quarto renderer. A local Quarto installation supports `quarto preview`.

## Fresh installation only

Create the public repository `adamdittrich.github.io`, set **Settings → Pages →
Source** to **GitHub Actions**, and upload the source including
`.github/workflows/publish.yml`. The website address is already configured.
