# Adam Dittrich, PhD — academic website

Updated 21 October 2026 for GitHub account `adamdittrich`.

## Publish this package

1. Sign in at <https://github.com> as `adamdittrich`.
2. Create a **public** repository named exactly `adamdittrich.github.io`. Initialise it with a README and use the default branch `main`.
3. Open **Settings → Pages → Build and deployment → Source** and select **GitHub Actions**. Skip suggested workflow templates: this package already contains one.
4. Extract the source ZIP. Upload the contents of `adam-dittrich-academic-site` to the repository root, including `.github`, `assets`, `_quarto.yml`, and the `.qmd` files. Do not upload the ZIP itself or nest the whole project inside an extra folder.
5. Commit the files to `main`. In **Actions**, open **Publish Quarto website**. If necessary, select **Run workflow → main → Run workflow**.
6. Wait for a successful build and deployment, then open <https://adamdittrich.github.io>.

The address in `_quarto.yml` is already configured. The workflow installs Quarto and builds the site on GitHub; a local Quarto installation is optional. The website has eight pages: seven main pages and a custom 404 page. The render selection excludes these project instructions from the public website.

GitHub's web uploader accepts at most 100 files at a time. The `docs` folder is generated output; it is optional for GitHub Actions publishing and can be omitted from the upload to reduce the file count. Keep the editable `.qmd` files, `_quarto.yml`, `.github`, and `assets`.

## Included CV

`assets/files/Adam-Dittrich-CV.pdf` is the general academic CV dated October 2026, created on 16 October 2026. It is linked from the homepage and CV page. The website records the PhD completed in September 2026, the defence on 29 September, and the Assistant Professor appointment from September 2026.

## Editing the site

| Content | Editable source |
| --- | --- |
| Homepage and news | `index.qmd` |
| Research | `research.qmd` |
| Publications and papers | `publications.qmd` |
| Data and replication | `data.qmd` |
| Teaching | `teaching.qmd` |
| Web CV | `cv.qmd` |
| Contact | `contact.qmd` |
| Downloadable CV | `assets/files/Adam-Dittrich-CV.pdf` |
| Bibliographic records | `assets/files/publications.bib` |
| Design | `assets/css/styles.css` |

Edit a source file on GitHub with the pencil button and commit to `main`; the site rebuilds automatically. The files in `docs/` are generated. For an accurate local preview with Quarto installed, run `quarto preview`. To rebuild the prepared HTML, run `quarto render`.

## Optional custom domain

Once you own a domain, add it under repository **Settings → Pages → Custom domain**, configure the registrar's DNS records using GitHub's instructions, update `website.site-url` in `_quarto.yml`, and enable HTTPS. A `CNAME` file alone does not configure a domain.

## Source record

See `SOURCE-NOTES.md` for the content sources and `LAUNCH-CHECKLIST.md` for the short launch checklist. The GitHub account has been identified from the screenshot supplied by Adam. This package does not itself create a repository or publish a website.
