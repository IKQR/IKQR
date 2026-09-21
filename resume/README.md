# Resume generator

Renders the profile Markdown files at the repo root (`Summary.md`, `SKILLS.md`,
`EXPERIENCE.md`, `PROJECTS.md`, `EDUCATION.md`, `CERTIFICATES.md`,
`LANGUAGES.md`) into a single PDF resume, so the CV never drifts out of sync
with the GitHub profile.

## Usage

```bash
pip install -r requirements.txt
RESUME_PHONE="+380..." RESUME_LOCATION="Ivano-Frankivsk, Ukraine" python scripts/generate_resume.py
```

All configuration is read from environment variables, each with a default in
`scripts/config.py`:

| Variable             | Default                                    |
|-----------------------|-------------------------------------------|
| `RESUME_FULL_NAME`    | `Illia Kusik`                              |
| `RESUME_TITLE`        | `Software Engineer & Tech Lead`            |
| `RESUME_LOCATION`     | *(empty - omitted from the PDF if unset)*  |
| `RESUME_EMAIL`        | `kusikillya2001@gmail.com`                 |
| `RESUME_PHONE`        | *(empty - omitted from the PDF if unset)*  |
| `RESUME_LINKEDIN_URL` | `https://www.linkedin.com/in/illia-kusik`  |
| `RESUME_LINKEDIN_LABEL` | `illia-kusik`                            |
| `RESUME_GITHUB_URL`   | `https://github.com/IKQR`                  |
| `RESUME_GITHUB_LABEL` | `IKQR`                                     |
| `RESUME_SPOTIFY_URL`  | `https://open.spotify.com/user/31gfjoy4c5moexolsj5veas2drhi` |
| `RESUME_SPOTIFY_LABEL` | `Spotify`                                 |

The output path is fixed at `output/Kusik_Illia_Resume.pdf` and isn't
configurable.

`RESUME_PHONE` and `RESUME_LOCATION` default to empty rather than being
hardcoded in `config.py` on purpose - private contact details aren't
committed to the repo. Set them in your shell (or an untracked `.env` you
source yourself) rather than editing the script.

## How parsing works

Each source file is parsed using the structured `## Heading` / `> date range`
/ `**Label**: value` / `---` conventions documented in the repo root
`CLAUDE.md`. If you follow those conventions when editing the `.md` files,
the generated PDF picks up the changes automatically - no changes to this
script are needed.

## CI: automated releases

`.github/workflows/release-cv.yml` regenerates the PDF and publishes it as a
GitHub release whenever a profile Markdown file or anything under `resume/`
changes on `main` (or on a manual `workflow_dispatch` run). It:

1. installs `fonts-dejavu-core` as a defensive font fallback, so any
   non-Latin text added to the profile Markdown later would still render
   correctly on the Linux runner instead of showing missing-glyph boxes;
2. runs `generate_resume.py`, reading `RESUME_PHONE` / `RESUME_LOCATION`
   from the `RESUME_PHONE` / `RESUME_LOCATION` repository secrets (optional -
   the PDF just omits them if the secrets aren't set, same as running
   locally with no env vars);
3. renames the output to `Kusik_Illia_CV_<year>_<month>.pdf`;
4. creates (or replaces, if the workflow already ran this month) a
   `cv-<year>-<month>` tag and GitHub release carrying that PDF as an asset.

To include your phone/location in the CI-built CV, add `RESUME_PHONE` and
`RESUME_LOCATION` under the repo's **Settings → Secrets and variables →
Actions**.
