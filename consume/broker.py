import requests
import urllib3
from decouple import config
urllib3.disable_warnings()       # only for dev!

CONNECTOR_BASE = config('CONNECTOR_BASE')
BROKER = config('BROKER')
AUTHORIZATION = config('AUTHORIZATION')

def get_all_connectors():
    """
    Fetch all connectors from the broker.

    Returns:
        dict: JSON-LD graph of connectors
    """
    url = f"{CONNECTOR_BASE}/api/ids/query"
    headers = {
        'Authorization': AUTHORIZATION,
        'Content-Type': 'application/octet-stream',
    }

    sparql = """\
PREFIX ids:   <https://w3id.org/idsa/core/>
PREFIX idsc:  <https://w3id.org/idsa/code/>
PREFIX owl:   <http://www.w3.org/2002/07/owl#>
PREFIX jsonld:<http://www.w3.org/ns/json-ld>

CONSTRUCT {
  ?connector ids:title           ?title.
  ?connector ids:description     ?description.
  ?connector ids:accessURL       ?accessURL.
  ?connector owl:sameAs          ?same.
  ?connector ids:maintainer      ?maintainer.
  ?connector ids:resourceCatalog ?connectorCatalog.
}
WHERE {
  ?connector ids:title              ?title.
  ?connector ids:description        ?description.
  ?connector ids:hasDefaultEndpoint ?endpoint.
  ?endpoint  ids:accessURL          ?accessURL.
  ?connector ids:maintainer         ?maintainer.
  OPTIONAL {
    ?connector ids:resourceCatalog  ?brokerCatalog.
    ?brokerCatalog owl:sameAs       ?connectorCatalog.
  }
  OPTIONAL { ?connector owl:sameAs  ?same. }
}
"""

    try:
        # Log request details (redact Authorization for safety)
        redacted_headers = headers.copy()
        if 'Authorization' in redacted_headers:
            redacted_headers['Authorization'] = '<REDACTED>'
        print('Posting to broker', url)
        print('Params:', {'recipient': BROKER})
        print('Headers:', redacted_headers)

        resp = requests.post(
            url,
            headers=headers,
            params={'recipient': BROKER},
            data=sparql.encode('utf-8'),
            verify=False
        )

        # If the server returns a non-2xx, capture body for debugging
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError:
            body_text = ''
            try:
                body_text = resp.text
            except Exception:
                body_text = '<unable to read response body>'

            # For 417 NOT_FOUND responses with empty broker index we treat it as "no connectors yet"
            if resp.status_code == 417:
                try:
                    payload = resp.json()
                except ValueError:
                    payload = {}

                reason = (
                    payload.get('details', {})
                           .get('reason', {})
                           .get('@id')
                )
                message = payload.get('message', '')
                if reason == 'https://w3id.org/idsa/code/NOT_FOUND':
                    print("Broker index reported empty. Returning no connectors.")
                    return {'@graph': []}

                print(f"Broker returned 417 response we could not map: {payload}")
            else:
                print(f"Broker returned error status {resp.status_code}")
                print("Response body:", body_text)

            return {
                'error': 'Broker returned error',
                'status_code': resp.status_code,
                'body': body_text
            }

        # Success path
        print("Response status code:", resp.status_code)
        print("Full response:", resp.text)
        try:
            return resp.json()
        except ValueError:
            # Not JSON — return raw text for inspection
            return {'@graph': [], 'raw': resp.text}

    except requests.exceptions.RequestException as e:
        print("Error fetching connectors:", e)
        return {"error": f"Failed to fetch connectors from the broker: {e}"}
