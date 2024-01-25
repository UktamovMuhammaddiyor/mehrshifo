from django.urls import path
from .views import index, setWebHook, getPost

urlpatterns = [
    path('', index, name="Home"),
    path('setwebhook/', setWebHook),
    path('getpost/', getPost),
]