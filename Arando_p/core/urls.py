from django.urls import path
from .views import estado_api

urlpatterns = [
    path('estado/', estado_api, name='estado_api'),
]