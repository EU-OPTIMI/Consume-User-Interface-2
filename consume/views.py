# consume/views.py

import json
import logging
import requests
from urllib.parse import urljoin, unquote
from decouple import config
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from .connector import runner
from .broker import get_all_connectors

# Configuration from .env
AUTHORIZATION = config('AUTHORIZATION')
BASE_URL      = config('BASE_URL')
PAGE_SIZE     = 30
AUTH_HEADERS  = {'Authorization': AUTHORIZATION}

logger = logging.getLogger(__name__)

WORKFLOW_SUMMARY_TEXT = {
    'Offer discovery': 'Offer metadata retrieved from the provider.',
    'Catalog lookup': 'Matched the offer to its catalog entry.',
    'Description request': 'Gathered IDS contract details.',
    'Contract negotiation': 'Confirmed usage agreement with the provider.',
    'Artifact agreement': 'Located the artifact endpoint.',
    'Artifact retrieval': 'Fetched the preview of the shared data.'
}

CITY_COORDS = {
    'Kokkola': (63.838, 23.130),
    'Seinäjoki': (62.790, 22.840),
    'Pori': (61.485, 21.797),
    'Naantali': (60.467, 22.026),
    'Kapellskär': (59.718, 19.060),
    'Nykvarn': (59.180, 17.430),
    'Kapelskär': (59.718, 19.060),  # common spelling variant
}

CITY_ALIASES = {
    'Naantali Hub': 'Naantali',
    'Kapellskär Port': 'Kapellskär',
    'Port': 'Naantali',
    'Ferry': 'Naantali',
}


def _derive_provider_ui_bases():
    """
    Build a prioritized list of Provider UI base URLs. If PROVIDER_UI_BASE is
    explicitly configured, prefer it. Otherwise try BASE_URL (which usually
    includes /connector) and the host root as a fallback.
    """
    configured = config('PROVIDER_UI_BASE', default='').strip()
    bases = []

    if configured:
        bases.append(configured.rstrip('/'))
    else:
        trimmed = BASE_URL.rstrip('/') if BASE_URL else ''
        if trimmed:
            bases.append(trimmed.rstrip('/'))
            suffix = '/connector'
            if trimmed.endswith(suffix):
                host_only = trimmed[:-len(suffix)]
                if host_only:
                    bases.append(host_only.rstrip('/'))

    # Remove empties while preserving order
    seen = set()
    ordered = []
    for base in bases:
        if base and base not in seen:
            ordered.append(base)
            seen.add(base)
    return ordered


PROVIDER_UI_BASES = _derive_provider_ui_bases()

PROVIDER_UI_AUTH = config('PROVIDER_UI_AUTHORIZATION', default='').strip()
PROVIDER_UI_HEADERS = {}
if PROVIDER_UI_AUTH:
    PROVIDER_UI_HEADERS['Authorization'] = PROVIDER_UI_AUTH


def _normalize_place_name(name):
    if not name:
        return None
    cleaned = name.split(':')[-1].strip()
    alias = CITY_ALIASES.get(cleaned)
    if alias:
        cleaned = alias
    return cleaned


def _split_leg_places(leg_name):
    if not leg_name:
        return (None, None)
    cleaned = leg_name.split(':')[-1]
    parts = cleaned.split(' to ')
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return cleaned.strip(), None


def _coords_for_place(name):
    if not name:
        return None
    normalized = CITY_ALIASES.get(name, name).replace('Hub', '').strip()
    return CITY_COORDS.get(normalized)


def _match_leg_emission(leg_label, start, end, emissions_map):
    if not emissions_map:
        return None
    candidates = []
    if leg_label:
        candidates.append(leg_label)
    if start and end:
        candidates.extend([
            f"{start} to {end}",
            f"{start} Hub to {end}",
            f"{start} to {end} Hub",
        ])
    for candidate in candidates:
        for key, value in emissions_map.items():
            if key.lower() == candidate.lower():
                return value
    return None


def _build_route_map(consumption):
    body = ((consumption or {}).get('response_preview') or {}).get('body')
    if not body:
        return None
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return None

    unified = payload.get('unified') or {}
    chains = unified.get('transportChains') or {}
    legs = []
    last_known_name = None
    last_known_coords = None

    for chain in chains.values():
        element = chain.get('transportChainElement') or {}
        for leg in element.get('transportLegs') or []:
            sequence = leg.get('sequence')
            leg_name = leg.get('legName')
            distance = leg.get('distance')
            start, end = _split_leg_places(leg_name)
            start = _normalize_place_name(start) or start
            end = _normalize_place_name(end) or end
            if not start and last_known_name:
                start = last_known_name
            if (leg_name or '').lower().startswith('ferry') and last_known_name:
                start = start or last_known_name
            start_coords = _coords_for_place(start)
            if not start_coords and last_known_coords:
                start_coords = last_known_coords
                if not start:
                    start = last_known_name

            end_coords = _coords_for_place(end)
            if not end_coords and end:
                cleaned = end.replace('Hub', '').strip()
                end_coords = _coords_for_place(cleaned)
            if not end_coords:
                alias = CITY_ALIASES.get(end)
                if alias:
                    end_coords = _coords_for_place(alias)
                    if not end:
                        end = alias

            if not start_coords or not end_coords:
                # can't map this leg; skip but continue tracking last known
                if end_coords:
                    last_known_coords = end_coords
                    last_known_name = end or last_known_name
                continue

            last_known_coords = end_coords
            last_known_name = end or start or last_known_name

            legs.append({
                'sequence': sequence,
                'start': start,
                'end': end,
                'start_coords': start_coords,
                'end_coords': end_coords,
                'distance': distance,
                'leg_label': leg_name
            })
    if not legs:
        return None

    legs.sort(key=lambda item: item.get('sequence') or 0)
    stops = []
    seen = set()

    for leg in legs:
        if leg['start'] and leg['start'] not in seen:
            lat, lng = leg['start_coords']
            stops.append({
                'name': leg['start'],
                'lat': lat,
                'lng': lng,
                'sequence': leg.get('sequence')
            })
            seen.add(leg['start'])
        if leg['end'] and leg['end'] not in seen:
            lat, lng = leg['end_coords']
            stops.append({
                'name': leg['end'],
                'lat': lat,
                'lng': lng,
                'sequence': (leg.get('sequence') or 0) + 0.1
            })
            seen.add(leg['end'])

    segments = []
    for leg in legs:
        segments.append({
            'from': leg['start'],
            'to': leg['end'],
            'distance': leg.get('distance'),
            'coords': [
                list(leg['start_coords']),
                list(leg['end_coords'])
            ]
        })

    lats = [stop['lat'] for stop in stops]
    lngs = [stop['lng'] for stop in stops]
    bounds = [
        [min(lats), min(lngs)],
        [max(lats), max(lngs)]
    ]

    shipment_fp = (unified.get('shipment') or {}).get('shipmentFootprint') or {}
    metrics = {
        'shipment_id': shipment_fp.get('shipmentId'),
        'parcel_id': ((shipment_fp.get('scope') or {}).get('parcelId')),
        'total_emissions': ((shipment_fp.get('totalEmissions') or {}).get('co2e')),
        'emissions_unit': ((shipment_fp.get('totalEmissions') or {}).get('unit')),
        'standard': shipment_fp.get('standardsUsed'),
        'calculated_at': shipment_fp.get('calculationTimestamp')
    }
    calc_dt = parse_datetime(metrics['calculated_at']) if metrics['calculated_at'] else None
    if calc_dt:
        metrics['calculated_at_human'] = calc_dt.strftime('%Y-%m-%d %H:%M')
    else:
        metrics['calculated_at_human'] = metrics['calculated_at']
    breakdown = shipment_fp.get('breakdown') or []
    leg_emissions = {}
    non_leg_hotspots = []
    for entry in breakdown:
        activity = entry.get('activity', '')
        if not activity:
            continue
        label = activity.split(':', 1)[-1].strip() if ':' in activity else activity
        co2e = entry.get('co2e')
        leg_emissions[label] = co2e

        is_transport_leg = 'transport leg' in activity.lower()
        if not is_transport_leg:
            non_leg_hotspots.append(entry)

    leg_details = []
    total_distance = 0
    enriched_segments = []
    for idx, leg in enumerate(legs):
        segment = segments[idx]
        leg_distance = leg.get('distance') or 0
        total_distance += leg_distance or 0
        emission_value = _match_leg_emission(
            leg.get('leg_label'),
            leg.get('start'),
            leg.get('end'),
            leg_emissions
        )
        leg_details.append({
            'sequence': leg.get('sequence'),
            'label': f"{leg.get('start')} → {leg.get('end')}",
            'distance': leg.get('distance'),
            'emissions': emission_value
        })
        segment_copy = segment.copy()
        segment_copy['emissions'] = emission_value
        enriched_segments.append(segment_copy)

    metrics['total_distance'] = total_distance

    return {
        'stops': stops,
        'segments': enriched_segments,
        'bounds': bounds,
        'metrics': metrics,
        'breakdown': non_leg_hotspots[:4],
        'leg_details': leg_details
    }


def _request_offer_extras(base_url, offer_id):
    paths = [
        f"{base_url.rstrip('/')}/api/offers/{offer_id}/extras/",
        f"{base_url.rstrip('/')}/provide/api/offers/{offer_id}/extras/"
    ]
    errors = []

    for extras_url in paths:
        result = _perform_extras_request(extras_url, offer_id, base_url)
        if result:
            if result['status'] == 'error':
                errors.append(result)
                continue
            return result

    return errors[-1] if errors else {
        'status': 'error',
        'error': 'Provider extras request failed',
    }


def _perform_extras_request(extras_url, offer_id, base_url):
    headers = PROVIDER_UI_HEADERS.copy()

    try:
        resp = requests.get(extras_url, headers=headers, verify=False, timeout=10)
    except requests.RequestException as exc:
        logger.warning("Offer extras request failed for %s (%s): %s", offer_id, extras_url, exc)
        return {
            'status': 'error',
            'error': str(exc),
            'url': extras_url,
            'base_url': base_url
        }

    if resp.status_code == 404:
        return {
            'status': 'not_found',
            'data_model': None,
            'purpose_of_use': None,
            'url': extras_url,
            'base_url': base_url
        }

    if resp.status_code != 200:
        logger.warning(
            "Offer extras unexpected status for %s (%s): %s %s",
            offer_id,
            extras_url,
            resp.status_code,
            resp.text[:200]
        )
        return {
            'status': 'error',
            'error': f"Unexpected status {resp.status_code}",
            'url': extras_url,
            'base_url': base_url
        }

    body = (resp.text or '').strip()
    if not body:
        return {
            'status': 'not_found',
            'data_model': None,
            'purpose_of_use': None,
            'url': extras_url,
            'base_url': base_url
        }

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning(
            "Offer extras invalid JSON for %s (%s): %s body=%s",
            offer_id,
            extras_url,
            exc,
            body[:150]
        )
        return {
            'status': 'error',
            'error': 'Invalid JSON payload',
            'url': extras_url,
            'base_url': base_url
        }

    return {
        'status': 'ok',
        'data_model': payload.get('data_model'),
        'purpose_of_use': payload.get('purpose_of_use'),
        'raw': payload,
        'url': extras_url,
        'base_url': base_url
    }


def _fetch_offer_extras(offer_id):
    """
    Call the Provider UI extras API for a given offer ID to pull data model
    and purpose of use fields when available. Try each derived base URL until
    we either succeed or exhaust options.
    """
    if not PROVIDER_UI_BASES:
        return {
            'status': 'disabled',
            'reason': 'PROVIDER_UI_BASE not configured'
        }

    last_error = None
    for base in PROVIDER_UI_BASES:
        result = _request_offer_extras(base, offer_id)
        if result['status'] in ('ok', 'not_found'):
            return result
        last_error = result

    return last_error or {
        'status': 'error',
        'error': 'Provider extras request failed'
    }


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

    policy_source = (
        offer.get('policy')
        or offer.get('usagePolicy')
        or offer.get('contract')
        or offer.get('license')
        or {}
    )
    if isinstance(policy_source, (dict, list)):
        policy_raw = json.dumps(policy_source, indent=2)
    else:
        policy_raw = policy_source or "No policy provided."
    policy_summary = (
        offer.get('policy_summary')
        or offer.get('policySummary')
        or offer.get('policyDescription')
        or "Review and agree to the provider's license/policy terms before consuming the offer."
    )

    # Try to consume offer immediately so the page can surface IDS workflow info
    offer_url = f"{BASE_URL.rstrip('/')}/api/offers/{raw_id}"
    should_consume = request.GET.get('consume') == '1'
    consumption = None
    consumption_error = None
    offer_extras = _fetch_offer_extras(raw_id)
    route_map = None

    if should_consume:
        try:
            consumption = runner(offer_url)
        except Exception as exc:
            consumption_error = str(exc)
        else:
            route_map = _build_route_map(consumption)

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
        'step_state': step_state,
        'offer_extras': offer_extras,
        'policy_raw': policy_raw,
        'policy_summary': policy_summary,
        'workflow_summary': [
            {
                'label': step.get('label', 'Workflow step'),
                'status': step.get('status', 'completed'),
                'message': WORKFLOW_SUMMARY_TEXT.get(
                    step.get('label'),
                    'Completed successfully.'
                )
            }
            for step in (consumption or {}).get('steps', [])
        ] if consumption else None,
        'route_map': route_map
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
