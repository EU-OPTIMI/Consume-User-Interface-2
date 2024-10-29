import requests
import json
from django.shortcuts import render
from .connector import get_selected_offer, runner

def connector_offers(request):
    page = request.GET.get('page', '1')
    size = request.GET.get('size', '10')
    
    # Construct the URL with pagination parameters
    url = f'https://ds2provider.collab-cloud.eu:8081/api/offers?page={page}&size={size}'
    headers = {
        'Authorization': 'Basic YWRtaW46cGFzc3dvcmQ='
    }
    
    response = requests.get(url, headers=headers)
    print("response: ", response)


    data = response.json()
    print('JSON RESPONSE', data)
    
    offers = data.get('_embedded', {}).get('resources', [])
    pagination_links = data.get('_links', {})
    page_info = data.get('page', {})
    
    
    offer_data = []
    for offer in offers:
        offer_url = offer['_links']['self']['href']
        offer_id = offer_url.split('/')[-1]
        offer_data.append({
            'offer_id': offer_id,
            'title': offer['title'],
            'description': offer['description'],
            'creationDate': offer['creationDate'],
            'modificationDate': offer['modificationDate'],
            'keywords': offer['keywords']
        })

    
    total_pages = page_info.get('totalPages', 1) - 1 #Can we remove like this the extra empty page?
    current_page = int(page_info.get('number', 1))
    page_range = range(1, total_pages + 1)
    print("Pagination Info:")
    print(f"Total Pages: {total_pages}, Current Page: {current_page}, Page Size: {size}")
    
    return render(request, 'consume/connector_offers.html', {
        'offers': offer_data,
        'pagination': {
            'first': pagination_links.get('first', {}).get('href', ''),
            'prev': pagination_links.get('prev', {}).get('href', ''),
            'next': pagination_links.get('next', {}).get('href', ''),
            'last': pagination_links.get('last', {}).get('href', ''),
            'current': pagination_links.get('self', {}).get('href', ''),
            'size': page_info.get('size', 10),
            'total_pages': total_pages,
            'current_page': current_page,
            'page_range': page_range
        }
    })

def selected_offer(request, offer_id):
    offer = get_selected_offer(offer_id)
    return render(request, 'consume/selected_offer.html', {'offer': offer, 'offer_id': offer_id})

def consume_offer(request, offer_id):
    offer_url = f"https://ds2provider.collab-cloud.eu:8081/api/offers/{offer_id}"
    artifact_url = runner(offer_url) 
    return render(request, 'consume/consume_offer.html',{'artifact_url': artifact_url})