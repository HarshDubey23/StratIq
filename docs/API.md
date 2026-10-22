# API (v1)

Base path `/api/v1`. Interactive docs at `/docs` on the backend. Auth: httpOnly cookie `siq_session` (JWT) set by
signup/login; `Authorization: Bearer` is also accepted. Every project-scoped route checks ownership and returns **404**
for other users' resources. Validation errors return `422 {"detail":"Validation failed","errors":[{field,message}]}`.
Provider failures return `502` with a readable message; failed simulations return `422` with `{message, run_id}` — never
a success with placeholder numbers. All routes are synchronous request/response; market refresh can take up to ~60 s.

| Method | Path | Notes |
|---|---|---|
| POST | /auth/signup · /auth/login · /auth/logout | sets/clears cookie |
| GET | /auth/me | |
| POST | /auth/password | change password |
| PUT | /auth/preferences | onboarding answers |
| DELETE | /auth/account | deletes user and all data |
| GET | /categories/archetypes · /categories/catalog | public |
| POST | /categories/resolve `{query, use_ai}` | free-text → category + archetype |
| GET | /categories/by-key/{key} | |
| GET | /market/search?q= · /market/reverse?lat=&lng= | Nominatim (throttled, cached) |
| GET | /system/capabilities · /sources | public |
| GET/POST | /projects | create = project + Location A + baseline scenario |
| GET/PATCH/DELETE | /projects/{id} | |
| POST | /projects/{id}/locations | up to 5 |
| PATCH/DELETE | /projects/{id}/locations/{lid} | catchment, manual population |
| POST | /projects/{id}/locations/{lid}/refresh | live snapshot (Overpass, WorldPop, ORS) |
| GET | /projects/{id}/market?location_id= | snapshot + competitors (PostGIS ST_DWithin) |
| POST | /projects/{id}/competitors | user-observed or hypothetical |
| PATCH/DELETE | /projects/{id}/competitors/{cid} | price, quality, active; delete only user-added |
| GET/POST | /projects/{id}/scenarios | `clone_from` to duplicate |
| PATCH/DELETE | /scenarios/{sid} | baseline cannot be deleted |
| POST | /scenarios/{sid}/reset | copy baseline inputs |
| POST | /scenarios/{sid}/runs | runs the model, stores input hash, seed, model version |
| GET | /scenarios/{sid}/runs · /simulation-runs/{rid} · /simulation-runs/{rid}/results | |
| GET | /projects/{id}/compare | latest run per scenario |
| GET | /projects/{id}/decisions?goal= | rule-based decision |
| POST | /projects/{id}/explain?goal= | optional grounded AI paraphrase |
| POST/GET | /projects/{id}/reports(?share=true) | snapshot reports |
| GET | /reports/{rid} · /shared/reports/{token} | share token is public, revocable |
| POST | /reports/{rid}/unshare | |
| POST/GET | /projects/{id}/actual-outcomes · /projects/{id}/monitor | WAPE vs baseline |
| POST | /demo | labelled offline demo project |
| GET | /api/health | DB check |
