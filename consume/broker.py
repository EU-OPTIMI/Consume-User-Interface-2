import requests
import urllib3
urllib3.disable_warnings()       # only for dev!

CONNECTOR_BASE = 'https://connector.collab-cloud.eu'
BROKER        = 'https://broker.collab-cloud.eu/broker/infrastructure/'
AUTHORIZATION = 'Basic YWRtaW46cGFzc3dvcmQ='  # …or Bearer eyJ…

def get_all_connectors():
    """
    Fetch all connectors from the broker.

    Returns:
        dict: JSON-LD graph of connectors
    """
    url = f"{CONNECTOR_BASE}/api/ids/query"
    headers = {
        'Authorization': AUTHORIZATION,
        'Content-Type':  'application/octet-stream',
    }

    # triple-quoted string preserves line breaks exactly
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
        resp = requests.post(
            url,
            headers=headers,
            params={'recipient': BROKER},
            data=sparql.encode('utf-8'),
            verify=False
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print("Error fetching connectors:", e)
        return {"error": "Failed to fetch connectors from the broker."}
