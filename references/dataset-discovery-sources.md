# Dataset discovery API sources

Last reviewed: 2026-09-01 UTC.

These sources document the public metadata endpoints used by
`scripts/data_discovery.py`. Search responses are leads only; they do not prove
license rights, data quality, fitness for a hypothesis, privacy compliance or
download permission.

| Provider | Implementation endpoint | Official documentation |
|---|---|---|
| DataCite | `https://api.datacite.org/dois` with dataset resource filtering | <https://support.datacite.org/docs/api-get-lists> |
| Zenodo | `https://zenodo.org/api/records` | <https://developers.zenodo.org/> |
| Hugging Face Hub | `https://huggingface.co/api/datasets` | <https://huggingface.co/docs/hub/api> |
| OpenML | `https://www.openml.org/api/v1/json/data/list/...` | <https://docs.openml.org/data/use/> |
| Figshare | `POST https://api.figshare.com/v2/articles/search` | <https://docs.figshare.com/v2/> |
| Dryad | `https://datadryad.org/api/v2/search` | <https://datadryad.org/api> |
| Harvard Dataverse | `https://dataverse.harvard.edu/api/search` with `type=dataset` | <https://guides.dataverse.org/en/latest/api/search.html> |
| Data.gov / CKAN | `https://catalog.data.gov/api/3/action/package_search` | <https://data.gov/old-user-guide/> and <https://docs.ckan.org/en/2.11/api/> |

Figshare public search uses a JSON POST body. All other listed searches use
bounded public HTTPS GET requests. The network layer rejects credentialed,
loopback, private, link-local and unsafe redirected URLs.

Kaggle is not enabled by default. Its official client requires separate Kaggle
account credentials and its dataset terms vary. Do not scrape it, store its key
in a project, or treat the UUAPI key as a Kaggle credential.

Review these documents and the provider changelogs before changing an endpoint
or response parser. Provider availability and response fields can change
without making an existing local research approval valid for new data.
