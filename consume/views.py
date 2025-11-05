# consume/views.py

import requests
from urllib.parse import urljoin, unquote
from decouple import config
from django.shortcuts import render, redirect
from django.urls import reverse
from .connector import runner
from .broker import get_all_connectors

# Configuration from .env
AUTHORIZATION = config('AUTHORIZATION')
BASE_URL      = config('BASE_URL')
PAGE_SIZE     = 30
AUTH_HEADERS  = {'Authorization': AUTHORIZATION}


def _fetch_all_pages(base_url, embedded_key):
    """
    Fetches every page of an IDS‐style paged endpoint,
    accumulating all entries under `_embedded[embedded_key]`.
    """
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
        # stop when we've reached the last page
        if pg.get('number', 0) >= pg.get('totalPages', 1) - 1:
            break

        page += 1

    return items


def dataspace_connectors(request):
    """
    List all offers from all connectors:
    - Normalize broker response into a list of connectors
    - For each connector, iterate all catalogs
    - For each catalog, iterate all offers
    """
    print("Fetching all connectors...")
    raw = get_all_connectors()
    if isinstance(raw, dict) and raw.get('error'):
        return render(request, 'consume/error.html', {
            'error': raw['error']
        })

    # Normalize into a list of connector dicts
    if isinstance(raw, dict) and '@graph' in raw:
        connectors = raw['@graph']
    elif isinstance(raw, dict):
        connectors = [raw]
    elif isinstance(raw, list):
        connectors = raw
    else:
        connectors = []

    offers = []

    for conn in connectors:
        connector_id = conn.get('@id')

        # Gather all sameAs endpoints (or fallback)
        endpoints = conn.get('sameAs') or []
        if isinstance(endpoints, str):
            endpoints = [endpoints]
        if not endpoints:
            endpoints = [urljoin(connector_id, 'api/catalogs')]

        for ep in endpoints:
            ep = ep.rstrip('/')
            catalogs_url = f"{ep}/api/catalogs"
            catalogs = _fetch_all_pages(catalogs_url, 'catalogs')

            for cat in catalogs:
                title = cat.get('title')
                desc  = cat.get('description')

                # Build and possibly rewrite the offers URL
                offers_href = (
                    cat.get('_links', {})
                       .get('offers', {})
                       .get('href', '')
                       .split('{')[0]
                )
                if '/connector/' not in offers_href and '/api/catalogs/' in offers_href:
                    offers_href = offers_href.replace(
                        '/api/catalogs/',
                        '/connector/api/catalogs/'
                    )

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

    return render(request, 'consume/connector_offers.html', {
        'offers': offers
    })


def selected_offer(request, offer_id):
    """
    Fetch the full details of one offer and render it.
    """
    raw_id = unquote(offer_id)
    try:
        url = f"{BASE_URL.rstrip('/')}/api/offers/{raw_id}"
        resp = requests.get(url, headers=AUTH_HEADERS, verify=False)
        resp.raise_for_status()
        offer = resp.json()
        offer['offer_url'] = url
        offer['offer_id']  = offer_id
    except requests.exceptions.RequestException as e:
        return render(request, 'consume/error.html', {
            'error': f"Failed to fetch offer {offer_id}: {e}"
        })

    # Try to consume offer immediately so the page can surface IDS workflow info
    offer_url = f"{BASE_URL.rstrip('/')}/api/offers/{raw_id}"
    should_consume = request.GET.get('consume') == '1'
    consumption = None
    consumption_error = None

    if should_consume:
        try:
            consumption = runner(offer_url)
        except Exception as exc:
            consumption_error = str(exc)

    # stepper state flags
    step_state = {
        'discover': True,
        'select': True,
        'explore': should_consume,
        'consume': consumption is not None,
        'consume_error': consumption_error is not None,
    }

    return render(request, 'consume/selected_offer.html', {
        'offer':    offer,
        'offer_id': offer_id,
        'should_consume': should_consume,
        'consumption': consumption,
        'consumption_error': consumption_error,
        'step_state': step_state
    })


def consume_offer(request, offer_id):
    """
    Given an offer ID, invoke runner() to consume it and render the artifact URL.
    """
    raw_id = unquote(offer_id)
    offer_url = f"{BASE_URL.rstrip('/')}/api/offers/{raw_id}"

    # Redirect to the unified selected_offer view with consume mode enabled
    target = f"{reverse('consume:selected_offer', args=[offer_id])}?consume=1"
    return redirect(target)
