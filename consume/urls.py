# consume/urls.py

from django.urls import path
from .views import dataspace_connectors, selected_offer, consume_offer

app_name = 'consume'

urlpatterns = [
    # GET /consume/                      → list all offers
    path(
        '',
        dataspace_connectors,
        name='connector_offers'
    ),

    # GET /consume/selected_offer/<id>/  → show one offer
    path(
        'selected_offer/<str:offer_id>/',
        selected_offer,
        name='selected_offer'
    ),

    # GET /consume/consume_offer/<id>/   → run consumption
    path(
        'consume_offer/<path:offer_id>/',
        consume_offer,
        name='consume_offer'
    ),
]