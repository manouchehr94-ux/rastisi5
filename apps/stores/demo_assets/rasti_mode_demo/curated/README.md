# Rasti Mode Demo curated visuals

Demo-only visual source pack for `rasti-mode-demo`.

- Store branding uses the user's approved RastiSi mark plus a clothing icon.
- Hero/banner/category photography is cropped from the AI-generated RastiSi fashion visuals approved in this conversation.
- The crops intentionally remove baked-in campaign copy where practical so the same media can be reused across different Ready Template renderers without duplicated headings.
- Six fictional demo-brand cards are generated locally and map to the existing fictional `Demo *` brand records.
- Product images are **not** replaced by this pack.
- The current newsletter subscriber model has no image field; this demo-only refresh does not introduce a second newsletter renderer or template-specific media branch.

Apply through:

```text
python manage.py refresh_rasti_mode_demo_visuals --check-only
python manage.py refresh_rasti_mode_demo_visuals
```

The command is `DEBUG=True` only and targets the exact fixed slug `rasti-mode-demo`.
