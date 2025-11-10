# Consume# Consume-User-Interface-2
# Consume-User-Interface-2

## Offer Extras Lookup

Before processing any offer, call the Provider UI extras API to retrieve the `data_model` and `purpose_of_use` values that are not provided with the connector metadata.

### Prompt for implementers

1. After the offer is published and you have the connector offer ID, call `GET https://<provider-host>/provide/api/offers/<offer_id>/extras/`.
2. If the response is 200, merge `data_model` and `purpose_of_use` into your offer payload under whatever fields you expose to downstream services.
3. If the response is 404, assume no additional metadata is stored and continue with defaults; log the miss for monitoring.

### Example

Request:

```
GET /provide/api/offers/123e4567-e89b-12d3-a456-426614174000/extras/
```

Response (200):

```json
{
  "offer_id": "123e4567-e89b-12d3-a456-426614174000",
  "data_model": "Common Information Model (CIM)",
  "purpose_of_use": "Analytics",
  "created_at": "2025-11-10T11:05:22.781Z",
  "updated_at": "2025-11-10T11:05:22.781Z"
}
```

Response (404):

```json
{
  "offer_id": "123e4567-e89b-12d3-a456-426614174000",
  "data_model": null,
  "purpose_of_use": null
}
```

### Notes

- No auth header is currently required inside the platform network; add bearer/basic auth if your deployment secures the Provider UI.
- Cache the extras per offer ID; they only change if the provider republishes.
- Log failures so we can spot missing metadata early.

### Application configuration

Set the following variables in `.env` (or your deployment secret store) so the consumer UI can run the lookup automatically during the consume flow:

- `PROVIDER_UI_BASE`: Base host for the Provider UI, e.g. `https://optimi.collab-cloud.eu`. The app appends `/provide/api/offers/<offer_id>/extras/`.
- `PROVIDER_UI_AUTHORIZATION` *(optional)*: If your Provider UI is secured, supply the bearer/basic header value that should be forwarded with the extras request.

If `PROVIDER_UI_BASE` is omitted, the consumer will first try `BASE_URL` itself (including `/connector` if present) and then fall back to the host root, so leave it unset unless your deployment hosts the Provider UI elsewhere.
