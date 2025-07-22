from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),

    # Mount your consume app at “/consume/” with a namespace
    path(
        'consume/',
        include(
            ('consume.urls', 'consume'),
            namespace='consume'
        )
    ),
]