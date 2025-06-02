from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('consume/', include('consume.urls')),
 #   path('', lambda request: redirect('/consume/connector_offers/', permanent=False)),
]