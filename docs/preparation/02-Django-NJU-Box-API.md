# Django and NJU Box API preparation

## Runtime

- Python 3.12
- Django 5.1.7
- No HTTP client dependency is required; upload uses Python standard-library HTTPS support.

## Local configuration

Copy `.env.example` to `.env` and set the following local-only values:

```dotenv
DJANGO_SECRET_KEY=replace-for-local-use
DJANGO_DEBUG=true
NJU_BOX_API_URL=https://box.nju.edu.cn
NJU_BOX_REPOSITORY_ID=e2304051-022d-43bd-b3f9-d4d34051a040
NJU_BOX_TARGET_DIRECTORY=/
NJU_BOX_API_TOKEN=your-personal-api-token
NJU_BOX_LIBRARY_PASSWORD=your-library-password
```

The app prefers `NJU_BOX_API_TOKEN` and `NJU_BOX_LIBRARY_PASSWORD` from `.env`. If either value is empty, the upload form supplies the missing value for that request. Neither value is stored in the database or session.
