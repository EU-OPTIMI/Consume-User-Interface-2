# views.py

import requests
from urllib.parse import urljoin
from decouple import config
from django.shortcuts import render
from .broker import get_all_connectors
from urllib.parse import unquote
from .connector import runner

AUTHORIZATION = config('AUTHORIZATION')
PAGE_SIZE     = 30
AUTH_HEADERS  = {'Authorization': AUTHORIZATION}
BASE_URL = config('BASE_URL')

def _fetch_all_pages(base_url, embedded_key):
    items = []
    page = 0

    while True:
        resp = requests.get(
            f"{base_url.rstrip('/')}?page={page}&size={PAGE_SIZE}",
            headers=AUTH_HEADERS,
            verify=False
        )
        resp.raise_for_status()
        payload = resp.json()

        batch = payload.get('_embedded', {}).get(embedded_key, [])
        items.extend(batch)

        pg = payload.get('page', {})
        # if we've reached last page, stop
        if pg.get('number', 0) >= pg.get('totalPages', 1) - 1:
            break
        page += 1

    return items


def dataspace_connectors(request):
    # 1) Fetch raw connector info
    raw = get_all_connectors()
    if isinstance(raw, dict) and raw.get('error'):
        return render(request, 'consume/error.html', {'error': raw['error']})

    # 2) Normalize to a list of connector dicts
    if isinstance(raw, dict) and '@graph' in raw:
        connectors = raw['@graph']
    elif isinstance(raw, dict):
        connectors = [raw]
    elif isinstance(raw, list):
        connectors = raw
    else:
        connectors = []

    offers = []

    # 3) Walk every connector
    for conn in connectors:
        connector_id = conn.get('@id')

        # collect all sameAs endpoints (or fallback)
        endpoints = conn.get('sameAs') or []
        if isinstance(endpoints, str):
            endpoints = [endpoints]
        if not endpoints:
            endpoints = [urljoin(connector_id, 'api/catalogs')]

        for ep in endpoints:
            ep = ep.rstrip('/')
            catalogs_url = f"{ep}/api/catalogs"
            # 4) Fetch every catalog
            catalogs = _fetch_all_pages(catalogs_url, 'catalogs')

            for cat in catalogs:
                title = cat.get('title')
                desc  = cat.get('description')

                # build the offers URL
                offers_href = (
                    cat.get('_links', {})
                       .get('offers', {})
                       .get('href', '')
                       .split('{')[0]
                )
                # ensure we’re going through the connector proxy if needed
                if '/connector/' not in offers_href and '/api/catalogs/' in offers_href:
                    offers_href = offers_href.replace(
                        '/api/catalogs/',
                        '/connector/api/catalogs/'
                    )

                # 5) Fetch every offer in that catalog
                resources = _fetch_all_pages(offers_href, 'resources')
                for off in resources:
                    self_href = (
                        off.get('_links', {})
                           .get('self', {})
                           .get('href', '')
                    )
                    offer_id = self_href.rstrip('/').split('/')[-1]
                    offers.append({
                        'connector_id':        connector_id,
                        'catalog_title':       title,
                        'catalog_description': desc,
                        'offer_title':         off.get('title'),
                        'offer_description':   off.get('description'),
                        'offer_keywords':      off.get('keywords', []),
                        'offer_publisher':     off.get('publisher'),
                        'offer_url':           self_href,
                        'offer_id':            offer_id,
                    })
                    print("offer_id", offer_id)

    return render(request, 'consume/connector_offers.html', {
        'offers': offers
    })

def selected_offer(request, offer_id):
    """
    Fetch the full details of one offer and render it.
    """
    try:
        url = f"{BASE_URL.rstrip('/')}/api/offers/{offer_id}"
        resp = requests.get(url, headers=AUTH_HEADERS, verify=False)
        resp.raise_for_status()
        offer = resp.json()
        # augment for your template
        offer['offer_url'] = url
        offer['offer_id']  = offer_id
    except requests.exceptions.RequestException as e:
        return render(request, 'consume/error.html', {
            'error': f"Failed to fetch offer {offer_id}: {e}"
        })

    return render(request, 'consume/selected_offer.html', {
        'offer':    offer,
        'offer_id': offer_id
    })


def consume_offer(request, offer_id):
    """
    Given an offer ID, run your runner() to kick off the consumption
    and render the resulting artifact URL.
    """
    # in case the ID is URL‐encoded
    raw_id = unquote(offer_id)
    offer_url = f"{BASE_URL.rstrip('/')}/api/offers/{raw_id}"

    try:
        artifact_url = runner(offer_url)
    except Exception as e:
        return render(request, 'consume/error.html', {
            'error': f"Failed to consume offer {raw_id}: {e}"
        })

    return render(request, 'consume/consume_offer.html', {
        'artifact_url': artifact_url
    })