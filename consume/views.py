import requests
import json
from django.shortcuts import render
from .connector import get_selected_offer, runner
from .broker import get_all_connectors
from urllib.parse import unquote
from decouple import config
from django.http import JsonResponse

    
AUTHORIZATION = config('AUTHORIZATION')
BASE_URL = config('BASE_URL')


def connector_offers(request):
    # Fetch connectors from the broker
    connectors_data = get_all_connectors()
    print('OOOOO', connectors_data)
    # Check if there was an error
    if "error" in connectors_data:
        return render(request, 'consume/error.html', {'error': connectors_data['error']})
    
    # Extract connectors and their catalogs
    offers = []
    for connector in connectors_data.get('@graph', []):
        print('CONNECTOR', connector)
        connector_id = connector.get('@id')
        catalogs = connector.get('resourceCatalog', [])
        print('CCCAATALOG######', catalogs)
        if isinstance(catalogs, str):
            catalogs = [catalogs]
            print('MMMM',catalogs)
        
        for catalog_url in catalogs:
            print('AAAAAAAAAA', catalog_url)
            # Fetch catalog details
            try:
                catalog_response = requests.get(
                    catalog_url,
                    headers={'Authorization': AUTHORIZATION},
                    verify=False
                )
                
                catalog_response.raise_for_status()
                catalog_data = catalog_response.json()
                
                # Fetch offers for the catalog
                offers_url = catalog_data['_links']['offers']['href'].split('{')[0]  # Remove templated part
                
                offers_response = requests.get(
                    offers_url,
                    headers={'Authorization': AUTHORIZATION},
                    verify=False
                )
                offers_response.raise_for_status()
                offers_data = offers_response.json()
                
                # Extract offer details
                for offer in offers_data.get('_embedded', {}).get('resources', []):
                    offer_url = offer['_links']['self']['href']
                    offer_id = offer_url.split('/')[-1]
                    
                    offers.append({
                        'connector_id': connector_id,
                        'catalog_title': catalog_data.get('title'),
                        'catalog_description': catalog_data.get('description'),
                        'offer_title': offer.get('title'),
                        'offer_description': offer.get('description'),
                        'offer_keywords': offer.get('keywords', []),
                        'offer_publisher': offer.get('publisher'),
                        'offer_url': offer_url,
                        'offer_id': offer_id
                    })
            except requests.exceptions.RequestException as e:
                print(f"Error fetching catalog or offers: {e}")
    
    # Render the updated template
    return render(request, 'consume/connector_offers.html', {'offers': offers})

def selected_offer(request, offer_id):
    try:
        offer = get_selected_offer(offer_id)
        offer['offer_url'] = f'{BASE_URL}api/offers/{offer_id}'
        offer['offer_id'] = offer_id  # <-- Add this
    except requests.exceptions.RequestException as e:
        print(f"Error fetching selected offer: {e}")
        return render(request, 'consume/error.html', {'error': 'Failed to fetch the selected offer.'})

    return render(request, 'consume/selected_offer.html', {'offer': offer, 'offer_id': offer_id})


def get_selected_offer(offer_id):
    url = f'{BASE_URL}api/offers/{offer_id}'
    headers = {
        'Authorization': 'Basic YWRtaW46cGFzc3dvcmQ='
    }
    
    response = requests.get(url, headers=headers, verify=False)
    response.raise_for_status()  # Raise an error if the request fails
    return response.json()



def consume_offer(request, offer_id):
    offer_id = unquote(offer_id)
    offer_url = f"{BASE_URL}api/offers/{offer_id}"
    
    artifact_url = runner(offer_url)
    print('Artifact URL:', artifact_url)
    
    return render(request, 'consume/consume_offer.html', {'artifact_url': artifact_url})


def dataspace_connectors(request):
    data = get_all_connectors()

    # Normalize data to a list
    if isinstance(data, dict) and "@graph" in data:
        connectors = data["@graph"]
    elif isinstance(data, dict):
        connectors = [data]
    else:
        connectors = data

    catalogs = {}
    for connector in connectors:
        print('CONNECTOR', connector)
        rc = connector.get("resourceCatalog")
        connector_id = connector.get("@id")
        if rc and connector_id:
            # Use first item if rc is a list, or rc directly if it's a string
            rc_url = rc if isinstance(rc, str) else rc[0]
            parts = rc_url.rstrip('/').split('/')
            url_without_uuid = '/'.join(parts[:-1]) + '/'
            catalogs[connector_id] = url_without_uuid

    offers_url_list = []
    offers = []

    for connector_id, url in catalogs.items():
        try:
            response = requests.get(
                url,
                headers={'Authorization': AUTHORIZATION},
                verify=False
            )
            if response.status_code == 200:
                catalog_data = response.json()
                for catalog in catalog_data.get("_embedded", {}).get("catalogs", []):
                    offers_link = catalog.get("_links", {}).get("offers", {}).get("href")
                    if offers_link:
                        clean_url = offers_link.split('{')[0]
                        offers_url_list.append({
                            'url': clean_url,
                            'connector_id': connector_id,
                            'catalog_title': catalog.get('title'),
                            'catalog_description': catalog.get('description')
                        })
            else:
                print(f"Failed to fetch from {url}, status code: {response.status_code}")
        except requests.RequestException as e:
            print(f"Request error for {url}: {e}")

    for offer_info in offers_url_list:
        try:
            response = requests.get(
                offer_info['url'],
                headers={'Authorization': AUTHORIZATION},
                verify=False
            )
            if response.status_code == 200:
                offers_data = response.json()
                for offer in offers_data.get('_embedded', {}).get('resources', []):
                    offer_url = offer['_links']['self']['href']
                    offer_id = offer_url.split('/')[-1]

                    offers.append({
                        'connector_id': offer_info['connector_id'],
                        'catalog_title': offer_info['catalog_title'],
                        'catalog_description': offer_info['catalog_description'],
                        'offer_title': offer.get('title'),
                        'offer_description': offer.get('description'),
                        'offer_keywords': offer.get('keywords', []),
                        'offer_publisher': offer.get('publisher'),
                        'offer_url': offer_url,
                        'offer_id': offer_id
                    })
            else:
                print(f"Failed to fetch offers from {offer_info['url']}, status code: {response.status_code}")
        except requests.RequestException as e:
            print(f"Request error for {offer_info['url']}: {e}")

    return render(request, 'consume/connector_offers.html', {'offers': offers})