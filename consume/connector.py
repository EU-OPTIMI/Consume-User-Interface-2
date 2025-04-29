import requests
import json
import re

from requests.auth import HTTPBasicAuth

def get_selected_offer(offer_id):
    url = f'https://connectorb:8081/api/offers/{offer_id}'
    headers = {
        'Authorization': 'Basic YWRtaW46cGFzc3dvcmQ='
    }
    
    response = requests.get(url, headers=headers, verify=False)
    offer = response.json()
    # Render the offer detail template with offer data
    return offer
    
def get_selected_offers_catalog_url(offer):
    catalog_url_with_pagination = offer["_links"]["catalogs"]["href"]
    catalog_url = re.sub(r'\{.*\}', '', catalog_url_with_pagination).strip()
    # Define the headers
    headers = {
        'accept': '*/*',
        'content': 'application/json',
        'Authorization': 'Basic YWRtaW46cGFzc3dvcmQ='
    }

    # Send the GET request
    print("catalog_url", catalog_url)
    response = requests.get(catalog_url, headers=headers, verify=False)
    response_json = response.json()
    catalog_url = response_json["_embedded"]["catalogs"][0]["_links"]["self"]["href"]
    return catalog_url

def description_request(offer, catalog_url):
    print("catalog_urlcatalog_url", catalog_url)
    url = 'https://connectorb:8081/api/ids/description'
    headers = {
        'Authorization': 'Basic YWRtaW46cGFzc3dvcmQ='
    }
    params = {
        'recipient': 'https://connectorb:8081/api/ids/data',
        'elementId': catalog_url
    }
    
    response = requests.post(url, headers=headers, params=params, verify=False)
    response_json = response.json()
    print('DESCRIPTION REQUEST RESPONSE:', response_json)
    action = response_json['ids:offeredResource'][0]['ids:contractOffer'][0]['ids:permission'][0]['ids:action'][0]['@id']
    artifact =response_json['ids:offeredResource'][0]['ids:representation'][0]['ids:instance'][0]['@id']
    return action, artifact
    
    

def contract_request(action, artifact, offer_id):
    url = 'https://connectorb:8081/api/ids/contract'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Basic YWRtaW46cGFzc3dvcmQ='
    }
    params = {
        'recipient': 'https://connectorb:8081/api/ids/data',
        'resourceIds': f"https://connectorb:8081/api/offers/{offer_id}",
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
    response_json = response.json()
    print('--------------------------------------------------------------------------------------------')
    print('CONTRACT REQUEST RESPONSE:', response_json)
    agreement_url_1 = response_json["_links"]["artifacts"]["href"]
    agreement_url = agreement_url_1.split('{')[0] 
    return agreement_url

def get_agreement(agreement_url):
    #url = f'https://connectorb:8081/api/agreements/{agreement_id}/artifacts'
    url = agreement_url
    headers = {
        'Authorization': 'Basic YWRtaW46cGFzc3dvcmQ='
    }

    response = requests.get(url, headers=headers, verify=False)
    response_json = response.json()
    print('EEEASYagreement',response_json)
    artifact_url = response_json["_embedded"]["artifacts"][0]["_links"]["data"]["href"]
        
    return artifact_url
    

def get_data(artifact_url):
    headers = {
        'Authorization': 'Basic YWRtaW46cGFzc3dvcmQ='
    }

    response = requests.get(artifact_url, headers=headers, verify=False)
    print('--------------------------------------------------------------')
    print('GEEEET DATA RESPONSE')
    print("Status Code:", response.status_code)
    print("Headers:", response.headers)
    print("Content:", response.content)  # Or use response.text for string output
    print("URL:", response.url)
    print('RESPONSE', response.text)
    return response

def runner(offer_url):
    offer_id = offer_url.split('/')[-1]
    print('OFFER ID', offer_id)
    offer = get_selected_offer(offer_id)
    print('OFFER', offer)
    catalog_url = get_selected_offers_catalog_url(offer)
    print('CATALOG URL', catalog_url)
    action, artifact = description_request(offer, catalog_url)
    print('ACTION', action)
    agreement_url = contract_request(action, artifact, offer_id)
    print('AGREEMENT URL', agreement_url)
    artifact_url = get_agreement(agreement_url)
    print('ARTIFACT URL', artifact_url)
    response = get_data(artifact_url)

    return artifact_url

    