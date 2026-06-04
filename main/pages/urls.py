from django.urls import path
from .views import index, setWebHook, getPost
from .miniapp.views import composer, api_generate, api_draft, api_publish

urlpatterns = [
    path('', index, name="Home"),
    path('setwebhook/', setWebHook),
    path('getpost/', getPost),
    path('miniapp/', composer),
    path('miniapp/api/generate', api_generate),
    path('miniapp/api/draft/<int:draft_id>', api_draft),
    path('miniapp/api/publish', api_publish),
]