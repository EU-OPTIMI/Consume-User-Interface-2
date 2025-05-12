import requests
import json
from django.shortcuts import render
from .connector import get_selected_offer, runner
from .broker import get_all_connectors
    
AUTHORIZATION = "Basic YWRtaW46cGFzc3dvcmQ="
def connector_offers(request):
    # Fetch connectors from the broker
    connectors_data = get_all_connectors()
    
    # Check if there was an error
    if "error" in connectors_data:
        return render(request, 'consume/error.html', {'error': connectors_data['error']})
    
    # Extract connectors and their catalogs
    offers = []
    for connector in connectors_data.get('@graph', []):
        connector_id = connector.get('@id')
        catalogs = connector.get('resourceCatalog', [])
        
        for catalog_url in catalogs:
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
    # Fetch the offer details using the offer_id
    try:
        offer = get_selected_offer(offer_id)
        # Add the offer URL to the offer object
        offer['offer_url'] = f'https://sandbox3.collab-cloud.eu/api/offers/{offer_id}'
    except requests.exceptions.RequestException as e:
        print(f"Error fetching selected offer: {e}")
        return render(request, 'consume/error.html', {'error': 'Failed to fetch the selected offer.'})
    
    # Render the selected offer template
    return render(request, 'consume/selected_offer.html', {'offer': offer, 'offer_id': offer_id})

def get_selected_offer(offer_id):
    url = f'https://sandbox3.collab-cloud.eu/api/offers/{offer_id}'
    headers = {
        'Authorization': 'Basic YWRtaW46cGFzc3dvcmQ='
    }
    
    response = requests.get(url, headers=headers, verify=False)
    response.raise_for_status()  # Raise an error if the request fails
    return response.json()

from urllib.parse import unquote

def consume_offer(request, offer_id):
    # Decode the offer_id if it's URL-encoded
    offer_url = unquote(offer_id)
    
    # Pass the offer_url to the runner function
    artifact_url = runner(offer_url)
    print('Artifact URL:', artifact_url)
    
    # Render the consume_offer template with the artifact URL
    return render(request, 'consume/consume_offer.html', {'artifact_url': artifact_url})