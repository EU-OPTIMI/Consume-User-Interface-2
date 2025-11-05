import json
import re
import logging

import requests
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

logger = logging.getLogger(__name__)


def get_selected_offer(offer_id):
    """
    Fetch the offer details for a given offer_id from the connector API.
    """
    url = f'{CONNECTOR_BASE}api/offers/{offer_id}'
    logger.info("Fetching offer %s at %s", offer_id, url)
    response = requests.get(url, headers=AUTH_HEADER, verify=False)
    logger.debug("Offer response status=%s headers=%s", response.status_code, response.headers)
    response.raise_for_status()
    offer = response.json()
    logger.debug("Offer payload: %s", json.dumps(offer, indent=2))
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
    logger.info("Fetching catalog listing from %s", catalog_url)
    response = requests.get(catalog_url, headers=headers, verify=False)
    logger.debug(
        "Catalog list response status=%s headers=%s",
        response.status_code,
        response.headers
    )
    if response.status_code != 200:
        logger.error(
            "Catalog request failed url=%s status=%s body=%s",
            catalog_url,
            response.status_code,
            response.text
        )
        raise ValueError(f"Failed to fetch catalog URL: {catalog_url}, Status Code: {response.status_code}")

    try:
        data = response.json()
    except json.JSONDecodeError as e:
        logger.exception(
            "Invalid JSON decoding catalog response url=%s body=%s",
            catalog_url,
            response.text
        )
        raise ValueError(f"Invalid JSON response from {catalog_url}")

    try:
        first_catalog = data["_embedded"]["catalogs"][0]
        catalog_self_href = first_catalog["_links"]["self"]["href"]
    except (KeyError, IndexError) as e:
        logger.error(
            "Catalog response missing expected structure. payload=%s error=%s",
            json.dumps(data, indent=2),
            e
        )
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
    logger.info("Issuing description request for catalog %s", catalog_url)
    url = f'{CONNECTOR_BASE}api/ids/description'
    headers = AUTH_HEADER.copy()
    params = {
        'recipient': f'{CONNECTOR_BASE}api/ids/data',
        'elementId': catalog_url
    }

    response = requests.post(url, headers=headers, params=params, verify=False)
    logger.debug(
        "Description response status=%s headers=%s body=%s",
        response.status_code,
        response.headers,
        response.text
    )
    response.raise_for_status()
    response_json = response.json()
    logger.debug("Description JSON: %s", json.dumps(response_json, indent=2))

    try:
        offered_resource = response_json['ids:offeredResource'][0]
        contract_offer = offered_resource['ids:contractOffer'][0]
        permission = contract_offer['ids:permission'][0]
        action = permission['ids:action'][0]['@id']
        representation = offered_resource['ids:representation'][0]
        artifact = representation['ids:instance'][0]['@id']
    except (KeyError, IndexError, TypeError) as exc:
        logger.error(
            "Description payload missing expected IDS fields: %s error=%s",
            json.dumps(response_json, indent=2),
            exc
        )
        raise ValueError("Description response missing IDS contract metadata") from exc

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

    logger.info(
        "Submitting contract request offer=%s artifact=%s action=%s",
        offer_id,
        artifact,
        action
    )
    response = requests.post(
        url,
        headers=headers,
        params=params,
        data=json.dumps(payload),
        verify=False
    )
    logger.debug(
        "Contract response status=%s headers=%s body=%s",
        response.status_code,
        response.headers,
        response.text
    )
    response.raise_for_status()
    response_json = response.json()
    logger.debug("Contract response JSON: %s", json.dumps(response_json, indent=2))
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
    logger.info("Fetching artifacts from %s", artifacts_url)
    response = requests.get(artifacts_url, headers=headers, verify=False)
    logger.debug(
        "Artifacts response status=%s headers=%s",
        response.status_code,
        response.headers
    )
    if response.status_code != 200:
        logger.error(
            "Artifacts request failed url=%s status=%s body=%s",
            artifacts_url,
            response.status_code,
            response.text
        )
        raise ValueError(f"Failed to fetch artifacts URL: {artifacts_url}, Status Code: {response.status_code}")

    try:
        data = response.json()
    except json.JSONDecodeError as e:
        logger.exception(
            "Invalid JSON decoding artifacts response url=%s body=%s",
            artifacts_url,
            response.text
        )
        raise ValueError(f"Invalid JSON response from {artifacts_url}")

    try:
        first_artifact = data["_embedded"]["artifacts"][0]
        artifact_href = first_artifact["_links"]["data"]["href"]
    except (KeyError, IndexError) as e:
        logger.error(
            "Artifacts response missing expected structure payload=%s error=%s",
            json.dumps(data, indent=2),
            e
        )
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
    logger.info("Fetching artifact payload from %s", artifact_url)
    logger.debug(
        "Artifact data response status=%s headers=%s body_preview=%s",
        response.status_code,
        response.headers,
        response.text[:500]
    )
    return response


def runner(offer_url):
    """
    Given a full offer_url, run the end-to-end sequence to get the artifact URL.
    """
    offer_id = offer_url.split('/')[-1]
    logger.info("Starting consumption pipeline for offer %s", offer_id)

    # Fetch the offer details
    offer = get_selected_offer(offer_id)
    logger.debug("Offer object: %s", json.dumps(offer, indent=2))

    # Get the catalog URL associated with the offer
    catalog_url = get_selected_offers_catalog_url(offer)
    logger.info("Resolved catalog URL %s", catalog_url)

    # Perform the description request
    action, artifact = description_request(offer, catalog_url)
    logger.info("Description request yielded action=%s artifact=%s", action, artifact)

    # Perform the contract request
    agreement_url = contract_request(action, artifact, offer_id)
    logger.info("Received agreement URL %s", agreement_url)

    # Get the artifact URL
    artifact_url = get_agreement(agreement_url)
    logger.info("Resolved artifact URL %s", artifact_url)

    # Optionally fetch the data (if needed)
    response = get_data(artifact_url)

    return artifact_url
