from django.urls import path
from .views import connector_offers, selected_offer, consume_offer

urlpatterns = [
    path('consume/connector_offers/', connector_offers, name='connector_offers'),
    path('consume/selected_offer/<str:offer_id>/', selected_offer, name='selected_offer'),
    path('consume/consume_offer/<path:offer_id>/', consume_offer, name='consume_offer'),  # Allow slashes in offer_id
]