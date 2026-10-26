# Third-party software

ShelfSort itself is MIT-licensed (see `LICENSE`). It uses the following libraries, each under its own license.
When ShelfSort is distributed as a bundled executable, the full license texts of these packages are included
next to the program (`licenses/` folder).

| Package | Version | License | Project |
|---|---|---|---|
| PySide6 (incl. PySide6-Essentials, PySide6-Addons, shiboken6) | 6.11.2 | LGPL-3.0 (used under LGPL) | https://pyside.org |
| guessit | 4.4.0 | LGPL-3.0-or-later | https://github.com/guessit-io/guessit |
| rebulk | 6.0.1 | MIT | https://github.com/Toilal/rebulk |
| babelfish | 0.6.1 | BSD-3-Clause | https://github.com/Diaoul/babelfish |
| python-dateutil | 2.9.0.post0 | Apache-2.0 / BSD-3-Clause | https://github.com/dateutil/dateutil |
| six | 1.17.0 | MIT | https://github.com/benjaminp/six |
| requests | 2.34.2 | Apache-2.0 | https://github.com/psf/requests |
| urllib3 | 2.8.0 | MIT | https://github.com/urllib3/urllib3 |
| idna | 3.20 | BSD-3-Clause | https://github.com/kjd/idna |
| charset-normalizer | 3.5.2 | MIT | https://github.com/jawah/charset_normalizer |
| certifi | 2026.7.22 | MPL-2.0 | https://github.com/certifi/python-certifi |
| Send2Trash | 2.1.0 | BSD-3-Clause | https://github.com/arsenetar/send2trash |

**LGPL note (PySide6, guessit):** these libraries are used unmodified and are kept as separate, replaceable files in
the distribution. Their source code is available at the project links above.

## Data sources

- **TMDB** – This product uses TMDB and the TMDB APIs but is not endorsed, certified, or otherwise approved by TMDB. https://www.themoviedb.org
- **Plex** – ShelfSort talks to your own Plex Media Server and to Plex's metadata service. ShelfSort is not
  affiliated with, endorsed or sponsored by Plex, Inc. "Plex" is a trademark of Plex, Inc.
