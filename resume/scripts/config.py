"""Contact header data that has no home in the profile markdown files.

Every value is read from an environment variable with a sane default, so
nothing here needs to be edited to regenerate the resume. Private details
such as the phone number and location default to empty - set RESUME_PHONE /
RESUME_LOCATION in your shell (not committed to the repo) rather than
hardcoding them here.
"""

import os


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


FULL_NAME = _env("RESUME_FULL_NAME", "Illia Kusik")
TITLE = _env("RESUME_TITLE", "Software Engineer & Tech Lead")
LOCATION = _env("RESUME_LOCATION", "")
EMAIL = _env("RESUME_EMAIL", "kusikillya2001@gmail.com")
PHONE = _env("RESUME_PHONE", "")
LINKEDIN_URL = _env("RESUME_LINKEDIN_URL", "https://www.linkedin.com/in/illia-kusik")
LINKEDIN_LABEL = _env("RESUME_LINKEDIN_LABEL", "illia-kusik")
GITHUB_URL = _env("RESUME_GITHUB_URL", "https://github.com/IKQR")
GITHUB_LABEL = _env("RESUME_GITHUB_LABEL", "IKQR")
SPOTIFY_URL = _env(
    "RESUME_SPOTIFY_URL",
    "https://open.spotify.com/user/31gfjoy4c5moexolsj5veas2drhi",
)
SPOTIFY_LABEL = _env("RESUME_SPOTIFY_LABEL", "Spotify")
