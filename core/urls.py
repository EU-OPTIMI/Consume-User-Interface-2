from django.contrib import admin
from django.urls import path, include
from core import views as core_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('logout/', core_views.auth_logout, name='auth_logout'),

    # Mount your consume app at “/consume/” with a namespace
    path(
        'consume/',
        include(
            ('consume.urls', 'consume'),
            namespace='consume'
        )
    ),
]
