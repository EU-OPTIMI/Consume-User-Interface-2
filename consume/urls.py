# consume/urls.py

from django.urls import path
from .views import dataspace_connectors, selected_offer, consume_offer

app_name = 'consume'

urlpatterns = [
    path('',                           dataspace_connectors, name='connector_offers'),
    path('selected_offer/<str:offer_id>/', selected_offer,  name='selected_offer'),
    path('consume_offer/<path:offer_id>/',  consume_offer,  name='consume_offer'),
]