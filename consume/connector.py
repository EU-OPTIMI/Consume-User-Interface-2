import requests
import json
import re
from decouple import config

# Read environment variables
CONNECTOR_BASE = config('CONNECTOR_BASE', default='').strip()
# Ensure CONNECTOR_BASE ends with exactly one slash
if CONNECTOR_BASE and not CONNECTOR_BASE.endswith('/'):
    CONNECTOR_BASE = CONNECTOR_BASE + '/'

# Fallback to BASE_URL if CONNECTOR_BASE is empty
BASE_URL = config('BASE_URL', default='').strip()
if BASE_URL and not BASE_URL.endswith('/'):
    BASE_URL = BASE_URL + '/'

if not CONNECTOR_BASE:
    CONNECTOR_BASE = BASE_URL

AUTH_HEADER = {
    'Authorization': config('AUTHORIZATION', default='').strip()
}

def get_selected_offer(offer_id):
    """
    Fetch the offer details for a given offer_id from the connector API.
    """
    url = f'{CONNECTOR_BASE}api/offers/{offer_id}'
    response = requests.get(url, headers=AUTH_HEADER, verify=False)
    response.raise_for_status()
    offer = response.json()
    return offer

def get_selected_offers_catalog_url(offer):
    """
    Given an offer JSON (with _links.catalogs.href), fetch the first catalog URL properly.
    This will rewrite broker URLs to the connector endpoint.
    """
    from urllib.parse import urlparse

    catalog_templated = offer["_links"]["catalogs"]["href"]
    # Strip off the templating {?page,size}
    templated_stripped = re.sub(r"\{.*\}", "", catalog_templated).strip()

    # Parse the path portion of the broker URL and rebuild under CONNECTOR_BASE
    parsed = urlparse(templated_stripped)
    path = parsed.path  # e.g. '/api/offers/{id}/catalogs'
    base_catalog = CONNECTOR_BASE + path.lstrip('/')

    # Ensure trailing slash
    if not base_catalog.endswith("/"):
        base_catalog = base_catalog + "/"

    # Add pagination parameters to get JSON
    catalog_url = f"{base_catalog}?page=0&size=10"

    headers = {
        'Accept': 'application/json',
        'Authorization': AUTH_HEADER['Authorization']
    }
    print(f"Fetching catalog URL: {catalog_url}")
    response = requests.get(catalog_url, headers=headers, verify=False)
    if response.status_code != 200:
        print(f"Failed to fetch catalog URL: {catalog_url}, Status Code: {response.status_code}")
        print(f"Response Text: {response.text}")
        raise ValueError(f"Failed to fetch catalog URL: {catalog_url}, Status Code: {response.status_code}")

    try:
        data = response.json()
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response from {catalog_url}: {e}")
        print(f"Response Text: {response.text}")
        raise ValueError(f"Invalid JSON response from {catalog_url}")

    try:
        first_catalog = data["_embedded"]["catalogs"][0]
        catalog_self_href = first_catalog["_links"]["self"]["href"]
    except (KeyError, IndexError) as e:
        print("Unexpected JSON structure:", data)
        raise ValueError("Could not find any catalog entries in the response.")

    # Rewrite the returned href under CONNECTOR_BASE as well
    parsed_self = urlparse(catalog_self_href)
    path_self = parsed_self.path  # e.g. '/api/catalogs/{catalogId}'
    rewritten_self = CONNECTOR_BASE + path_self.lstrip('/')

    return rewritten_self

def description_request(offer, catalog_url):
    """
    Perform an IDS description request for the given catalog_url.
    """
    print("catalog_urlcatalog_url", catalog_url)
    url = f'{CONNECTOR_BASE}api/ids/description'
    headers = AUTH_HEADER.copy()
    params = {
        'recipient': f'{CONNECTOR_BASE}api/ids/data',
        'elementId': catalog_url
    }

    response = requests.post(url, headers=headers, params=params, verify=False)
    response.raise_for_status()
    response_json = response.json()
    print('DESCRIPTION REQUEST RESPONSE:', response_json)
    action = response_json['ids:offeredResource'][0]['ids:contractOffer'][0]['ids:permission'][0]['ids:action'][0]['@id']
    artifact = response_json['ids:offeredResource'][0]['ids:representation'][0]['ids:instance'][0]['@id']
    return action, artifact

def contract_request(action, artifact, offer_id):
    """
    Perform an IDS contract request given an action, artifact, and offer_id.
    """
    url = f'{CONNECTOR_BASE}api/ids/contract'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': AUTH_HEADER['Authorization']
    }
    params = {
        'recipient': f'{CONNECTOR_BASE}api/ids/data',
        'resourceIds': f"{CONNECTOR_BASE}api/offers/{offer_id}",
        'artifactIds': artifact,
        'download': 'false'
    }
    payload = [
        {
            "@type": "ids:Permission",
            "ids:action": [
                {
                    "@id": action
                }
            ],
            "ids:target": artifact
        }
    ]

    response = requests.post(url, headers=headers, params=params, data=json.dumps(payload), verify=False)
    response.raise_for_status()
    response_json = response.json()
    print('--------------------------------------------------------------------------------------------')
    print('CONTRACT REQUEST RESPONSE:', response_json)
    agreement_url_1 = response_json["_links"]["artifacts"]["href"]
    agreement_url = agreement_url_1.split('{')[0]

    # Ensure full prefix
    if agreement_url.startswith("/"):
        agreement_url = CONNECTOR_BASE + agreement_url.lstrip('/')
    elif not agreement_url.startswith("http"):
        agreement_url = CONNECTOR_BASE + agreement_url

    return agreement_url

def get_agreement(agreement_url):
    """
    Retrieve the artifact URL from an agreement.
    This adds pagination parameters and rewrites any broker paths under CONNECTOR_BASE.
    """
    from urllib.parse import urlparse

    # Strip off any templated parts (e.g., {?page,size}), then parse path
    parsed_input = urlparse(agreement_url)
    path_input = parsed_input.path  # e.g. '/api/agreements/{id}/artifacts'
    base_artifacts = CONNECTOR_BASE + path_input.lstrip('/')

    # Ensure trailing slash
    if not base_artifacts.endswith("/"):
        base_artifacts = base_artifacts + "/"

    # Add pagination to get JSON
    artifacts_url = f"{base_artifacts}?page=0&size=10"

    headers = {
        'Accept': 'application/json',
        'Authorization': AUTH_HEADER['Authorization']
    }
    print(f"Fetching artifacts URL: {artifacts_url}")
    response = requests.get(artifacts_url, headers=headers, verify=False)
    if response.status_code != 200:
        print(f"Failed to fetch artifacts URL: {artifacts_url}, Status Code: {response.status_code}")
        print(f"Response Text: {response.text}")
        raise ValueError(f"Failed to fetch artifacts URL: {artifacts_url}, Status Code: {response.status_code}")

    try:
        data = response.json()
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response from {artifacts_url}: {e}")
        print(f"Response Text: {response.text}")
        raise ValueError(f"Invalid JSON response from {artifacts_url}")

    try:
        first_artifact = data["_embedded"]["artifacts"][0]
        artifact_href = first_artifact["_links"]["data"]["href"]
    except (KeyError, IndexError) as e:
        print("Unexpected JSON structure:", data)
        raise ValueError("Could not find any artifact entries in the response.")

    # Rewrite the returned href under CONNECTOR_BASE if needed
    parsed_art = urlparse(artifact_href)
    path_art = parsed_art.path  # e.g. '/api/artifacts/{artifactId}/data'
    rewritten_art = CONNECTOR_BASE + path_art.lstrip('/')

    return rewritten_art

def get_data(artifact_url):
    """
    Fetch the actual data at the artifact URL.
    """
    headers = AUTH_HEADER.copy()

    response = requests.get(artifact_url, headers=headers, verify=False)
    print('--------------------------------------------------------------')
    print('GEEEET DATA RESPONSE')
    print("Status Code:", response.status_code)
    print("Headers:", response.headers)
    print("Content:", response.content)  # Or use response.text
    print("URL:", response.url)
    print('RESPONSE', response.text)
    return response

def runner(offer_url):
    """
    Given a full offer_url, run the end-to-end sequence to get the artifact URL.
    """
    offer_id = offer_url.split('/')[-1]
    print('OFFER ID:', offer_id)

    # Fetch the offer details
    offer = get_selected_offer(offer_id)
    print('OFFER:', offer)

    # Get the catalog URL associated with the offer
    catalog_url = get_selected_offers_catalog_url(offer)
    print('CATALOG URL:', catalog_url)

    # Perform the description request
    action, artifact = description_request(offer, catalog_url)
    print('ACTION:', action)

    # Perform the contract request
    agreement_url = contract_request(action, artifact, offer_id)
    print('AGREEMENT URL:', agreement_url)

    # Get the artifact URL
    artifact_url = get_agreement(agreement_url)
    print('ARTIFACT URL:', artifact_url)

    # Optionally fetch the data (if needed)
    response = get_data(artifact_url)

    return artifact_url